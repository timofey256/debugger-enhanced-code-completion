from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.get("/health")
def health():
    return "ok", 200

@app.post("/debug")
def debug():
    data = request.get_json(force=True)
    # TODO: do an actual query
    diff = """diff --git a/sample.py b/sample.py
index e69de29..4b825dc 100644
--- a/sample.py
+++ b/sample.py
@@ -1,3 +1,3 @@
-def add(a, b):
-    return a - b
+def add(a, b):
+    return a + b
"""
    return diff, 200, {"Content-Type": "text/plain; charset=utf-8"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5123"))
    app.run("127.0.0.1", port, debug=False)
