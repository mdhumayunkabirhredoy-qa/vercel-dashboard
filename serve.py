"""
Quant Dashboard Server — serves HTML + API endpoints
Run: python serve.py
Access: http://144.31.227.43:8080
"""
import http.server
import json
import os
import sys
import importlib.util

PORT = 8080
BASE = os.path.dirname(os.path.abspath(__file__))

# Dynamically load API modules
API_MODULES = {}
api_dir = os.path.join(BASE, "api")
for fname in os.listdir(api_dir):
    if fname.endswith(".py"):
        name = fname[:-3]
        spec = importlib.util.spec_from_file_location(name, os.path.join(api_dir, fname))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        API_MODULES[name] = mod
        print(f"  Loaded API: /api/{name}")


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE, **kwargs)

    def do_GET(self):
        path = self.path.split("?")[0]
        
        # API routes
        if path.startswith("/api/"):
            api_name = path[5:]  # strip /api/
            if api_name in API_MODULES:
                mod = API_MODULES[api_name]
                try:
                    # Each module has a fetch_* function
                    func_name = None
                    for attr in dir(mod):
                        if attr.startswith("fetch_"):
                            func_name = attr
                            break
                    if func_name:
                        data = getattr(mod, func_name)()
                    else:
                        data = {"error": "no fetch function"}
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
                return
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"API {api_name} not found"}).encode())
                return
        
        # Serve index.html for root
        if path == "/" or path == "":
            self.path = "/index.html"
        
        # Serve public files
        if path.startswith("/public/"):
            self.path = path
        
        super().do_GET()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  QUANT DASHBOARD SERVER")
    print(f"  http://144.31.227.43:{PORT}")
    print(f"  APIs: {list(API_MODULES.keys())}")
    print(f"{'='*60}\n")
    
    server = http.server.HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
