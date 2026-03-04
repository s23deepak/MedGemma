# Firebase Setup Guide for MedGemma

## Step 1: Create a Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Click **"Create a project"** (or "Add project")
3. Enter project name: `medgemma-cure`
4. Disable Google Analytics (not needed) → click **Continue**
5. Wait for the project to be created → click **Continue**

## Step 2: Enable Firestore Database

1. In the left sidebar, click **"Build" → "Firestore Database"**
2. Click **"Create database"**
3. Select **"Start in test mode"** (allows read/write for 30 days — fine for dev)
4. Choose your nearest location (e.g., `nam5 (us-central)`) → click **Enable**

## Step 3: Enable Firebase Storage

1. In the left sidebar, click **"Build" → "Storage"**
2. Click **"Get started"**
3. Select **"Start in test mode"** → click **Next**
4. Confirm the location → click **Done**

## Step 4: Download Service Account Key

1. Click the **gear icon ⚙️** next to "Project Overview" in the sidebar
2. Click **"Project settings"**
3. Go to the **"Service accounts"** tab
4. Click **"Generate new private key"** → confirm
5. A JSON file will download (e.g., `medgemma-xxxxx-firebase-adminsdk-xxxxx-xxxxxxxxxx.json`)
6. **Move this file to your project root:**

```bash
mv ~/Downloads/medgemma-*-firebase-adminsdk-*.json ~/MedGemma/firebase-key.json
```

> ⚠️ **NEVER commit this file to Git.** It's already in `.gitignore`.

## Step 5: Set Environment Variable

Add to your `.env` file (or export in terminal):

```bash
echo 'FIREBASE_KEY_PATH=firebase-key.json' >> ~/MedGemma/.env
```

## Step 6: Seed the Database

Once the key is in place, run:

```bash
cd ~/MedGemma
uv run python scripts/seed_firebase.py
```

This pushes the 2 demo patients (P001 Sarah Wilson, P002 Carlos Martinez) with all their conditions, medications, allergies, and observations into Firestore.

## Step 7: Verify

```bash
uv run python main.py --use-vllm
```

Open http://localhost:8000 — the app now reads from Firestore instead of hardcoded data.

## Step 8: Enable Shared Medical Vocabulary Cache (Recommended)

The local health trends module can store external MeSH-enriched vocabulary in Firestore so all app instances share one cache.

Add to your `.env`:

```bash
echo 'MEDICAL_VOCAB_CACHE_BACKEND=firestore' >> ~/MedGemma/.env
```

Optional vector toggle:

```bash
echo 'MEDICAL_VOCAB_VECTOR_BACKEND=in_memory' >> ~/MedGemma/.env
```

This creates/uses:
- `system_cache/medical_vocab_mesh`

## Firestore Collections Structure

```
patients/
  P001/
    name: "Sarah M Wilson"
    gender: "female"
    birthDate: "1968-03-15"
    conditions/ → [Asthma, Hypertension]
    medications/ → [Albuterol, Lisinopril]
    allergies/ → [Penicillin]
    observations/ → [BP, HR, O2, Smoking]
    appointments/ → [latest appointment]
  P002/
    name: "Carlos Martinez"
    ...

system_cache/
  medical_vocab_mesh/
    fetched_at: "2026-..."
    source: "NLM MeSH Lookup API"
    event_categories: {...}
    symptom_synonyms: {...}
```

---

## New Firestore Collections (Auto-created)

The following collections are created automatically when Firebase is enabled and the app runs:

```
audit_log/
  AUD-{12-char-hex}/        ← one document per audit event
    event_id: "AUD-abc123..."
    timestamp: "2026-02-26T10:30:00"
    event_type: "SOAP_GENERATED"   # or COUNCIL_DELIBERATION / HANDOFF_GENERATED / DISCHARGE_PLANNED
    action: "generate_soap"
    patient_id: "P001"
    user_id: "system"
    success: true

hospitals/
  GENERAL/                   ← General Hospital, Chicago (pre-seeded)
    hospital_id: "GENERAL"
    name: "General Hospital"
    timezone: "America/Chicago"
    formulary_restrictions: []
    features_enabled: {audit_log: true, prior_auth: true, referral: true, simulation: true}
    contact_info: {phone: "555-0100", address: "123 Medical Dr, Chicago IL"}
  COMMUNITY/                 ← Community Medical Center, New York (pre-seeded)
    hospital_id: "COMMUNITY"
    formulary_restrictions: ["adalimumab", "pembrolizumab"]
    features_enabled: {audit_log: true, prior_auth: false, referral: true, simulation: false}
    ...
```

All Firestore writes are **fire-and-forget** — a Firestore failure never blocks the clinical workflow. When Firebase is unavailable:
- Audit events stay in-memory (ring buffer, last 1000 events)
- Hospital registry stays in-memory (pre-seeded GENERAL + COMMUNITY always available)
- Prior auth requests and referral letters are not persisted across restarts
