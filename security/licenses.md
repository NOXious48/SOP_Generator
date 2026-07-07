# Model & Dataset License Register (owner: Chesta; design AR-3)

> Verify each before commercial deployment. "Commercial OK" is indicative — confirm current terms.

## Models
| Component | License | Commercial OK | Notes |
|-----------|---------|---------------|-------|
| PaddleOCR | Apache-2.0 | Yes | OCR engine |
| Tesseract | Apache-2.0 | Yes | OCR fallback |
| Grounding DINO | Apache-2.0 | Yes | open-vocab detection |
| SAM2 | Apache-2.0 | Yes | segmentation |
| LayoutLMv3 | CC BY-NC-SA 4.0 | **No (non-commercial)** | needs replacement or license for commercial use |
| Florence-2 | MIT | Yes | detection/caption |
| Qwen2.5-VL | Apache-2.0 (check size variant) | Usually yes | confirm per checkpoint |
| Llama 3.2 (Ollama) | Llama Community License | Conditional | MAU threshold applies |

## Datasets
| Dataset | License | Commercial OK | Notes |
|---------|---------|---------------|-------|
| RICO | research use | Review | UI element data |
| Screen2Words | research use | Review | captions |
| PubLayNet | CDLA-Permissive / research | Review | layout |
| DocVQA | research use | Review | doc QA eval |
| ScreenSpot | research use | Review | grounding eval |
| Mind2Web | research use | Review | web workflow eval |

## Actions
- **LayoutLMv3 is non-commercial** — for a commercial product, replace with an Apache/MIT layout
  model (e.g., a Florence-2 / Pix2Struct-based layout path) or obtain a commercial license.
- Datasets used for **evaluation only** are lower risk than those used for **training**; training on
  research-only data for a shipped model requires legal review.
- Record the exact checkpoint + license URL at pin time in the model registry.
