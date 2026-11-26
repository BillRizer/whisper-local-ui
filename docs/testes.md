# Verification strategy

Install development dependencies and run:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The suite in `tests/test_app.py` exercises formats, model lifecycle, API, persistence, and MCP with a simulated transcriber. It does not demonstrate transcription accuracy, real CUDA operation, real model-weight downloads, browser recording, or complete security. For changes in these areas, add appropriate manual verification and record the environment, steps, and results in the PR; do not include private audio in fixtures. For visual changes, also check loading and error states in a browser.

Regression criteria: invalid input rejection, MCP file preservation, upload cleanup, export, persistence, and queue behavior must remain tested when affected. Security changes require tests of the trust boundary. CI runs the suite on CPU with dependencies installed; it is not proof of real-model or GPU operation.
