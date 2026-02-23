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
```
