"""
Tests for src/soap/generator.py — SOAPGenerator, EnhancedSOAPNote
"""


SAMPLE_SOAP_TEXT = """Subjective: Patient presents with a persistent cough for 5 days and low-grade fever.
Objective: Temp 100.4F, HR 88, BP 128/82. Lung auscultation reveals bilateral crackles.
Assessment: Suspected community-acquired pneumonia.
Plan: Start amoxicillin 500mg TID for 7 days. Chest X-ray ordered. Follow-up in 3 days."""


class TestSOAPParsing:
    def test_parse_soap_sections(self, soap_generator):
        note = soap_generator.parse_from_text(SAMPLE_SOAP_TEXT)
        assert note.subjective != ""
        assert note.objective != ""
        assert note.assessment != ""
        assert note.plan != ""


class TestEnhancedSOAPNote:
    def test_to_dict_has_all_keys(self):
        from src.soap.generator import EnhancedSOAPNote
        note = EnhancedSOAPNote(
            subjective="Cough for 5 days",
            objective="Temp 100.4",
            assessment="Pneumonia suspected",
            plan="Antibiotics"
        )
        d = note.to_dict()
        for key in ("subjective", "objective", "assessment", "plan"):
            assert key in d

    def test_to_markdown_has_headers(self):
        from src.soap.generator import EnhancedSOAPNote
        note = EnhancedSOAPNote(
            subjective="Cough",
            objective="Temp 100.4",
            assessment="Pneumonia",
            plan="Antibiotics"
        )
        md = note.to_markdown()
        assert "Subjective" in md
        assert "Objective" in md
        assert "Assessment" in md
        assert "Plan" in md

    def test_to_html_has_tags(self):
        from src.soap.generator import EnhancedSOAPNote
        note = EnhancedSOAPNote(
            subjective="Cough",
            objective="Temp 100.4",
            assessment="Pneumonia",
            plan="Antibiotics"
        )
        html = note.to_html()
        assert "<" in html  # has HTML tags


class TestSOAPGeneration:
    def test_generate_template(self, soap_generator):
        template = soap_generator.generate_template(
            chief_complaint="persistent cough",
            transcription="Patient has had cough for 5 days with fever",
            patient_context={"patient": {"name": "John Doe", "age": 55}}
        )
        assert "cough" in template.lower()

    def test_generate_enhanced_soap(self, soap_generator):
        note = soap_generator.generate_enhanced_soap(
            transcription="Patient complains of chest pain and shortness of breath for 2 days",
            patient_context={
                "patient": {"name": "Jane Doe", "age": 60},
                "conditions": [{"name": "Hypertension"}],
                "medications": [{"name": "Lisinopril 10mg"}]
            }
        )
        assert note is not None
        assert note.subjective != "" or note.assessment != ""
