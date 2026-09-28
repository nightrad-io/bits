import requests
import base64
import os
import sys
import json
import re
from urllib.parse import urlparse, quote
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding as rsa_padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

class RouterAuth:
    def __init__(self, url, username, password):
        self.base_url = url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.token = None
        self.sid = None
        self.public_key_obj = None
        
        # Common headers for router web interfaces
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        })

    def _custom_b64encode(self, data):
        """
        Custom Base64 encoding for 'ck', 'enckey', and 'enciv'.
        Maps: + -> -, / -> _, = -> .
        Preserves padding (as dots).
        """
        encoded = base64.b64encode(data).decode('utf-8')
        encoded = encoded.replace('+', '-').replace('/', '_').replace('=', '.')
        return encoded

    def _base64url_encode(self, data):
        """
        Standard Base64Url encoding for 'ct'.
        Maps: + -> -, / -> _
        STRIPS padding (no = or .).
        Matches sjcl.codec.base64url.fromBits.
        """
        return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

    def _load_public_key(self, pub_key_data):
        """
        Parses the public key. Handles PEM format.
        """
        try:
            if "-----BEGIN PUBLIC KEY-----" not in pub_key_data:
                pub_key_data = f"-----BEGIN PUBLIC KEY-----\n{pub_key_data}\n-----END PUBLIC KEY-----"
            
            return serialization.load_pem_public_key(
                pub_key_data.encode('utf-8'),
                backend=default_backend()
            )
        except Exception as e:
            print(f"[!] Failed to parse Public Key: {e}")
            raise

    def get_encryption_material(self):
        """
        Fetches nonce and public key from the router.
        """
        target_url = f"{self.base_url}/login_web_app.cgi?nonce"
        print(f"[*] Fetching encryption material from: {target_url}")
        
        try:
            resp = self.session.get(target_url, verify=False, timeout=10)
            resp.raise_for_status()
            
            try:
                data = resp.json()
            except json.JSONDecodeError:
                print("[!] Response is not valid JSON. Attempting regex extraction...")
                nonce_match = re.search(r'nonce\s*[:=]\s*["\']?([^"\',\}]+)', resp.text)
                pubkey_match = re.search(r'public_key\s*[:=]\s*["\']?([^"\',\}]+)', resp.text)
                
                if nonce_match and pubkey_match:
                    data = {
                        "nonce": nonce_match.group(1),
                        "public_key": pubkey_match.group(1)
                    }
                else:
                    raise ValueError("Could not extract nonce/key from response.")

            return data.get('nonce'), data.get('public_key') or data.get('pubkey')

        except Exception as e:
            print(f"[!] Error fetching encryption material: {e}")
            sys.exit(1)

    def _encrypt_and_bundle(self, plaintext, pub_key_obj):
        """
        Helper to encrypt payload with AES and key with RSA.
        Returns ct (AES payload) and ck (RSA key bundle).
        """
        # Generate new Session Keys
        session_key = os.urandom(16)
        iv = os.urandom(16)

        # AES-128-CBC with PKCS7 Padding for Payload
        padder = sym_padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext.encode('utf-8')) + padder.finalize()
        
        cipher = Cipher(algorithms.AES(session_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
        
        # 'ct' uses Base64Url with NO padding (stripped)
        ct = self._base64url_encode(encrypted_data)

        # RSA Encrypt the Key Bundle
        # Format: Base64(Key) + " " + Base64(IV)
        key_b64 = base64.b64encode(session_key).decode('utf-8')
        iv_b64 = base64.b64encode(iv).decode('utf-8')
        rsa_payload = f"{key_b64} {iv_b64}".encode('utf-8')
        
        encrypted_key_bundle = pub_key_obj.encrypt(
            rsa_payload,
            rsa_padding.PKCS1v15()
        )
        # 'ck' uses Custom encoding (dots for padding)
        ck = self._custom_b64encode(encrypted_key_bundle)
        
        return ct, ck, session_key, iv

    def login(self):
        # Step 1: Get Nonce and Public Key
        nonce, pub_key_pem = self.get_encryption_material()
        if not nonce or not pub_key_pem:
            print("[-] Failed to retrieve Nonce or Public Key.")
            return False

        print(f"[+] Got Nonce (Raw): {nonce}")
        
        # Apply custom encoding mapping to the nonce string
        if nonce:
            nonce = nonce.replace('+', '-').replace('/', '_').replace('=', '.')
            
        print(f"[+] Got Nonce (Encoded): {nonce}")
        
        self.public_key_obj = self._load_public_key(pub_key_pem)

        # Step 2: Generate Session Keys temporarily for plaintext injection
        session_key = os.urandom(16)
        iv = os.urandom(16)
        
        # 'enckey' and 'enciv' use the Custom encoding (dots for padding)
        enc_key_param = self._custom_b64encode(session_key)
        enc_iv_param = self._custom_b64encode(iv)
        
        # Step 3: Construct Plaintext
        plaintext = (
            f"userhash={quote(self.username)}&"
            f"RandomKeyhash=0&"
            f"response={quote(self.password)}&"
            f"nonce={nonce}&"
            f"enckey={enc_key_param}&"
            f"enciv={enc_iv_param}&"
            f"nohash=1&"
            f"hPassword=undefined"
        )
        
        print(f"[*] Generated Login Plaintext: {plaintext}")

        # Step 4 & 5: Encrypt (Using the logic, but we need to match the specific keys generated above)
        # Since _encrypt_and_bundle generates NEW keys, we must do this manually to match enckey/enciv
        
        # AES Encrypt
        padder = sym_padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext.encode('utf-8')) + padder.finalize()
        cipher = Cipher(algorithms.AES(session_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
        ct = self._base64url_encode(encrypted_data)

        # RSA Encrypt
        key_b64 = base64.b64encode(session_key).decode('utf-8')
        iv_b64 = base64.b64encode(iv).decode('utf-8')
        rsa_payload = f"{key_b64} {iv_b64}".encode('utf-8')
        encrypted_key_bundle = self.public_key_obj.encrypt(rsa_payload, rsa_padding.PKCS1v15())
        ck = self._custom_b64encode(encrypted_key_bundle)

        # Step 6: Send POST Request
        post_data = {
            "encrypted": "1",
            "ct": ct,
            "ck": ck
        }
        
        login_url = f"{self.base_url}/login_web_app.cgi"
        print(f"[*] Sending Login POST to {login_url}...")
        
        try:
            resp = self.session.post(login_url, data=post_data, verify=False)
            print(f"[*] Login Response Code: {resp.status_code}")
            # print(f"[*] Login Response Body: {resp.text}")
            
            if '"result":0' in resp.text:
                print("[+] Authentication Successful!")
                try:
                    data = resp.json()
                    self.sid = data.get('sid')
                    self.token = data.get('token')
                    print(f"    SID: {self.sid}")
                    print(f"    Token: {self.token}")
                    return True
                except:
                    print("[-] Failed to parse token from response.")
            else:
                print("[-] Authentication Failed.")
                print(f"    Response: {resp.text}")
                
        except Exception as e:
            print(f"[!] Login request failed: {e}")
        
        return False

    def send_ping(self, target_ip):
        if not self.token:
            print("[-] Cannot perform ping: Missing CSRF Token (Login failed?)")
            return

        # Prepare Payload
        # We assume the same transport encryption is used
        plaintext = (
            f"ipversion=ipv4&"
            f"iface=ip,1,1,1&"
            f"ipaddr={quote(target_ip)}&"
            f"checkall=trace&"
            f"pingcount=4&"
            f"packetlength=64&"
            f"tracehops=30&"
            f"csrf_token={self.token}"
        )
        
        print(f"[*] Generated Ping Plaintext: {plaintext}")

        # Encrypt Payload (AES) and Key (RSA)
        # We can reuse the public key stored during login
        ct, ck, _, _ = self._encrypt_and_bundle(plaintext, self.public_key_obj)

        post_data = {
            "encrypted": "1",
            "ct": ct,
            "ck": ck
        }

        ping_url = f"{self.base_url}/diag_web_app.cgi?ping"
        print(f"[*] Sending Ping/Trace to {ping_url}...")

        try:
            resp = self.session.post(ping_url, data=post_data, verify=False)
            print(f"[*] Ping Response Code: {resp.status_code}")
            print(f"[*] Ping Response Body:\n{resp.text}")
        except Exception as e:
            print(f"[!] Ping request failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python3 router_auth.py <router_url> <username> <password> <target_ip>")
        print("Example: python3 router_auth.py http://192.168.178.1 admin mypassword google.com")
        sys.exit(1)

    url = sys.argv[1]
    user = sys.argv[2]
    pwd = sys.argv[3]
    target = sys.argv[4]

    # Suppress SSL warnings for self-signed router certs
    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

    client = RouterAuth(url, user, pwd)
    if client.login():
        print("-" * 30)
        client.send_ping(target)
