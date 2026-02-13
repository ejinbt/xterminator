import requests
import os
import config

def test_proxy():
    proxy = os.getenv("PROXY_URL")
    if not proxy:
        print("No PROXY_URL set.")
        return

    print(f"Testing proxy: {proxy}")
    proxies = {
        "http": proxy,
        "https": proxy
    }
    
    try:
        # Test 1: Check IP
        print("Checking IP...")
        r = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=10)
        print(f"IP Response: {r.json()}")
        
        # Test 2: Check Twitter connectivity (headers are important)
        print("Checking Twitter connectivity...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r_tw = requests.get("https://twitter.com", proxies=proxies, headers=headers, timeout=10)
        print(f"Twitter Status Code: {r_tw.status_code}")
        print(f"Twitter URL: {r_tw.url}")
        
        if r_tw.status_code != 200:
            print("WARNING: Twitter returned non-200 status code.")
            # print(r_tw.text[:500]) # Print beginning of response to see if it's a block page
        else:
            print("Twitter connection successful.")
            
    except Exception as e:
        print(f"Proxy test failed: {e}")

if __name__ == "__main__":
    test_proxy()
