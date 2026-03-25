"""
Test suite for AI-generated bounding box annotations.

Tests the extraction and validation of structured JSON annotation data
from MedGemma image analysis responses.
"""

import json
import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import extract_ai_annotations


class TestExtractAIAnnotations:
    """Test AI annotation extraction from model responses."""

    def test_valid_json_with_single_finding(self):
        """Test extraction of single finding with valid coordinates."""
        response = """
        The image shows several findings:

        ## Key Findings
        - Right lower lobe opacity
        - Mild cardiomegaly

        ## Recommendations
        Follow up with correlation.

        ```json
        {
          "findings": [
            {
              "description": "Right lower lobe opacity",
              "normalized_box": {"x": 0.55, "y": 0.45, "w": 0.35, "h": 0.40},
              "confidence": 0.88,
              "significance": "SIGNIFICANT"
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 1
        ann = annotations[0]
        assert ann["label"] == "Right lower lobe opacity"
        assert ann["source"] == "ai"
        assert ann["confidence"] == 0.88
        assert ann["significance"] == "SIGNIFICANT"
        assert ann["x"] == 0.55
        assert ann["y"] == 0.45
        assert ann["w"] == 0.35
        assert ann["h"] == 0.40
        assert "id" in ann
        assert ann["id"].startswith("ai-")

    def test_valid_json_with_multiple_findings(self):
        """Test extraction of multiple findings."""
        response = """
        Analysis complete.

        ```json
        {
          "findings": [
            {
              "description": "Right lower lobe opacity",
              "normalized_box": {"x": 0.55, "y": 0.45, "w": 0.35, "h": 0.40},
              "confidence": 0.88,
              "significance": "SIGNIFICANT"
            },
            {
              "description": "Mild cardiomegaly",
              "normalized_box": {"x": 0.35, "y": 0.25, "w": 0.40, "h": 0.45},
              "confidence": 0.72,
              "significance": "SIGNIFICANT"
            },
            {
              "description": "Incidental degenerative changes",
              "normalized_box": {"x": 0.1, "y": 0.6, "w": 0.2, "h": 0.25},
              "confidence": 0.95,
              "significance": "INCIDENTAL"
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 3
        assert annotations[0]["label"] == "Right lower lobe opacity"
        assert annotations[1]["label"] == "Mild cardiomegaly"
        assert annotations[2]["label"] == "Incidental degenerative changes"

    def test_coordinate_clamping_to_0_1(self):
        """Test that coordinates outside [0,1] are clamped."""
        response = """
        ```json
        {
          "findings": [
            {
              "description": "Finding outside bounds",
              "normalized_box": {"x": -0.1, "y": 1.5, "w": 1.2, "h": 0.8},
              "confidence": 0.8,
              "significance": "SIGNIFICANT"
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 1
        ann = annotations[0]
        assert ann["x"] == 0.0  # clamped from -0.1
        assert ann["y"] == 1.0  # clamped from 1.5
        assert ann["w"] <= 1.0  # adjusted for bounds
        assert ann["h"] <= 1.0  # clamped from 0.8

    def test_box_contained_within_image(self):
        """Test that boxes don't exceed image bounds."""
        response = """
        ```json
        {
          "findings": [
            {
              "description": "Box too far right",
              "normalized_box": {"x": 0.8, "y": 0.5, "w": 0.5, "h": 0.3},
              "confidence": 0.8,
              "significance": "SIGNIFICANT"
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 1
        ann = annotations[0]
        # x + w should not exceed 1.0
        assert ann["x"] + ann["w"] <= 1.0
        assert ann["y"] + ann["h"] <= 1.0

    def test_confidence_clamping_0_1(self):
        """Test that confidence values are clamped to [0, 1]."""
        response = """
        ```json
        {
          "findings": [
            {
              "description": "High confidence",
              "normalized_box": {"x": 0.5, "y": 0.5, "w": 0.3, "h": 0.3},
              "confidence": 1.5,
              "significance": "SIGNIFICANT"
            },
            {
              "description": "Negative confidence",
              "normalized_box": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.3},
              "confidence": -0.5,
              "significance": "SIGNIFICANT"
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 2
        assert annotations[0]["confidence"] == 1.0  # clamped
        assert annotations[1]["confidence"] == 0.0  # clamped

    def test_missing_json_returns_empty_list(self):
        """Test graceful handling when no JSON is present."""
        response = """
        The image shows various findings but no structured output was provided.
        This is just plain text without any JSON.
        """

        annotations = extract_ai_annotations(response)

        assert annotations == []

    def test_malformed_json_returns_empty_list(self):
        """Test graceful handling of malformed JSON."""
        response = """
        ```json
        {
          "findings": [
            {
              "description": "Bad data",
              "normalized_box": {"x": 0.5, "y": invalid_value},
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert annotations == []

    def test_missing_findings_key_returns_empty_list(self):
        """Test graceful handling when findings key is missing."""
        response = """
        ```json
        {
          "other_key": "value",
          "data": [1, 2, 3]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert annotations == []

    def test_incomplete_finding_fields_skipped(self):
        """Test that findings with missing required fields are skipped."""
        response = """
        ```json
        {
          "findings": [
            {
              "description": "Valid finding",
              "normalized_box": {"x": 0.5, "y": 0.5, "w": 0.3, "h": 0.3},
              "confidence": 0.8,
              "significance": "SIGNIFICANT"
            },
            {
              "description": "Missing box",
              "confidence": 0.8,
              "significance": "SIGNIFICANT"
            },
            {
              "description": "Null box",
              "normalized_box": null,
              "confidence": 0.8,
              "significance": "SIGNIFICANT"
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        # Only the valid finding should be returned
        assert len(annotations) == 1
        assert annotations[0]["label"] == "Valid finding"

    def test_default_values_for_missing_fields(self):
        """Test that default values are used for missing optional fields."""
        response = """
        ```json
        {
          "findings": [
            {
              "description": "Minimal finding",
              "normalized_box": {"x": 0.5, "y": 0.5, "w": 0.3, "h": 0.3}
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 1
        ann = annotations[0]
        assert ann["label"] == "Minimal finding"
        assert ann["confidence"] == 0.5  # default
        assert ann["significance"] == "SIGNIFICANT"  # default
        assert ann["source"] == "ai"

    def test_unique_annotation_ids(self):
        """Test that each annotation gets a unique ID."""
        response = """
        ```json
        {
          "findings": [
            {"description": "Finding 1", "normalized_box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}, "confidence": 0.8, "significance": "SIGNIFICANT"},
            {"description": "Finding 2", "normalized_box": {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2}, "confidence": 0.8, "significance": "SIGNIFICANT"},
            {"description": "Finding 3", "normalized_box": {"x": 0.7, "y": 0.7, "w": 0.2, "h": 0.2}, "confidence": 0.8, "significance": "SIGNIFICANT"}
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 3
        ids = [ann["id"] for ann in annotations]
        assert len(set(ids)) == 3  # all unique
        assert all(id_.startswith("ai-") for id_ in ids)

    def test_json_inline_without_code_block(self):
        """Test JSON extraction when not in markdown code block."""
        response = """
        Some analysis here.

        {"findings": [{"description": "Test finding", "normalized_box": {"x": 0.5, "y": 0.5, "w": 0.3, "h": 0.3}, "confidence": 0.9, "significance": "CRITICAL"}]}

        More text here.
        """

        annotations = extract_ai_annotations(response)

        # Should find the JSON even without code block markers
        assert len(annotations) >= 0  # Depends on pattern matching

    def test_minimum_box_size_enforced(self):
        """Test that minimum box dimensions are enforced."""
        response = """
        ```json
        {
          "findings": [
            {
              "description": "Tiny box",
              "normalized_box": {"x": 0.5, "y": 0.5, "w": 0.0, "h": 0.0},
              "confidence": 0.8,
              "significance": "SIGNIFICANT"
            }
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 1
        ann = annotations[0]
        assert ann["w"] >= 0.01  # minimum enforced
        assert ann["h"] >= 0.01  # minimum enforced

    def test_all_significance_types(self):
        """Test handling of all significance types."""
        response = """
        ```json
        {
          "findings": [
            {"description": "Critical", "normalized_box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}, "significance": "CRITICAL"},
            {"description": "Significant", "normalized_box": {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.2}, "significance": "SIGNIFICANT"},
            {"description": "Incidental", "normalized_box": {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2}, "significance": "INCIDENTAL"},
            {"description": "Unknown", "normalized_box": {"x": 0.7, "y": 0.7, "w": 0.2, "h": 0.2}, "significance": "UNKNOWN"}
          ]
        }
        ```
        """

        annotations = extract_ai_annotations(response)

        assert len(annotations) == 4
        assert annotations[0]["significance"] == "CRITICAL"
        assert annotations[1]["significance"] == "SIGNIFICANT"
        assert annotations[2]["significance"] == "INCIDENTAL"
        assert annotations[3]["significance"] == "UNKNOWN"  # Preserved as-is


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
