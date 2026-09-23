# WORKFLOW DIFF: SUCCESS (ROI-LOCKED) VS PRODUCTION (13-CATEGORY TEST)

## Workflow Architecture Comparison
The overall architecture of the `ReferenceLatent-Klein-4b-Q8` graph used in the successful `roi_locked_runner.py` and the failed `category_sample_test_runner.py` is identical. 

- **ImageScaleToTotalPixels:** Identical (1.0 megapixels)
- **VAEEncode:** Identical
- **ReferenceLatent (Positive/Negative):** Identical
- **CLIPTextEncode:** Identical usage
- **ConditioningZeroOut:** Identical
- **EmptyFlux2LatentImage:** Identical (768x768, batch size 1)
- **RandomNoise:** Identical (Seed passed dynamically)
- **Flux2Scheduler:** Identical (4 steps)
- **CFGGuider:** Identical (cfg: 1.0)
- **SamplerCustomAdvanced:** Identical (euler)
- **VAEDecode:** Identical
- **SaveImage:** Identical

## Critical Difference Found: LoadImage Node and Upload Logic

The critical difference lies in how the `LoadImage` node's input filename was handled during the API upload sequence:

**Successful Run (`roi_locked_runner.py`):**
```python
comfy_name = f"roi_temp_{uuid.uuid4().hex[:8]}.png"
# Explicitly sets a unique filename for every API request
# LoadImage node receives a unique filename string
```

**Production Run (`category_sample_test_runner.py`):**
```python
def upload_image(filepath, subfolder="", overwrite=True):
    with open(filepath, "rb") as f:
        files = {"image": f} # Implicitly uses os.path.basename(f.name)
        # LoadImage node receives exactly "2_roi_reference.png" every time
```

### Consequence: Aggressive ComfyUI Caching
Because the production runner implicitly uploaded every cropped image using the exact same filename (`2_roi_reference.png`), the ComfyUI execution engine encountered a `LoadImage` node with identical input arguments across all 13 API requests.

ComfyUI caches node execution based on input parameters. After the very first generation (5 BALI 18), ComfyUI cached the loaded tensor for `2_roi_reference.png`. For the subsequent 12 items, even though the file on disk was overwritten, ComfyUI did not re-execute `LoadImage`. It passed the cached pixels of the very first item (5 BALI 18) down the pipeline. 

This resulted in a total disconnect between the text prompt (describing item N) and the reference pixels (stuck on item 1), forcing the model to hallucinate entirely new designs based solely on the generic text descriptions to resolve the conflict.
