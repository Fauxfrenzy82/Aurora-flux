"""Quick test to verify Deriv API token works."""
import asyncio
import json
import websockets

APP_ID = "33b1ep15QNRAi49QORAdF"
TOKEN = "pat_e08714d87ff445a52987854fa9e49912e8825475b125ef35729b62c50116be68"

async def test():
    url = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"
    print(f"Connecting to Deriv...")
    
    try:
        ws = await websockets.connect(url)
        print("Connected!")
        
        # Authorize
        await ws.send(json.dumps({"authorize": TOKEN}))
        resp = json.loads(await ws.recv())
        print(f"Auth Response: {json.dumps(resp, indent=2)}")
        
        if resp.get("error"):
            print(f"\n❌ AUTH FAILED: {resp['error']}")
            print("\nPossible causes:")
            print("1. Token scopes wrong — needs Read + Trade + Trading Information + Payments")
            print("2. Account not activated for API — log into app.deriv.com first")
            print("3. Token was created for wrong app type — needs PAT (Personal Access Token)")
        else:
            print("\n✅ AUTH SUCCESSFUL!")
            
            # Get balance
            await ws.send(json.dumps({"balance": 1}))
            bal = json.loads(await ws.recv())
            print(f"Balance: {json.dumps(bal, indent=2)}")
        
        await ws.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

asyncio.run(test())