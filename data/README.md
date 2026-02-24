# Demo Images for MedGemma Clinical Assistant

## Other Data Assets

- `medical_dictionary_terms.json` — local fallback medical lexicon for trend correlation
- `medical_vocab_cache.json` — local cache of externally enriched medical vocabulary (auto-generated)

## Sample Medical Images

For the demo, you can download sample chest X-ray images from:

### NIH Chest X-ray Dataset (Public Domain)
- Download: https://nihcc.app.box.com/v/ChestXray-NIHCC
- Contains 100,000+ de-identified chest X-rays
- Public domain with attribution required

### Quick Sample Download (for demo)
Download a few sample images manually and place them in `data/sample_images/`

### Kaggle Dataset
- https://www.kaggle.com/datasets/nih-chest-xrays/data
- Same dataset, easier to browse

## Attribution Required
When using NIH images, include:
- Link to NIH download site
- Citation to Wang et al., CVPR 2017
- Acknowledge NIH Clinical Center

## Demo Scenario
For the competition demo, use an image that shows:
- Chest X-ray with subtle findings (e.g., small nodule, mild infiltrate)
- This allows MedGemma to demonstrate "missed diagnosis" detection
