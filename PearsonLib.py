import base64
import requests
import random
import string
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
from Crypto.Cipher import PKCS1_v1_5, AES
from tqdm import tqdm

def decode_and_import_rsa_private_key(data):
    private_key_bytes = base64.b64decode(base64.b64decode(data.encode()))
    rsa_private_key = RSA.import_key(private_key_bytes)
    return rsa_private_key


class Pearson:
    def __init__(self, username=None, password=None):
        self.session = requests.Session()
        self.device_id = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
        self.client_id = "t1txmB9oRay3yK5aIQxsS28Z9T19xMLM"
        self.access_token = None
        self.username = username
        self.password = password

    def login(self):
        login_url = "https://api.pearson.com/v1/piapi/login/webcredentials"
        headers = {
            "User-Agent": f"mobile_app|{{\"browser\":\"Android Device\",\"device\":\"Phone\",\"display\":\"Custom\",\"id\":\"{self.device_id}\",\"os\":\"Android\"}}",
            "Host": "login.pearson.com"
        }
        data = {
            "password": self.password,
            "username": self.username,
            "isMobile": "true",
            "grant_type": "password",
            "client_id": self.client_id
        }
        response = self.session.post(login_url, headers=headers, data=data).json()

        self.access_token = response.get("data").get("access_token")
        if self.access_token:
            self.session.headers["Authorization"] = f"Bearer {self.access_token}"
            return True
        return False

    def get_bookshelf(self):
        response = self.session.get("https://marin-api.prd-prsn.com/api/1.0/bookshelf").json()
        return response

    def download_book(self, book_id, filename, show_progress=False):
        device_info = self.session.get(
            f"https://marin-api.prd-prsn.com/api/1.0/capi/ddk/device/{self.device_id}").json()

        private_key = decode_and_import_rsa_private_key(device_info["signature-ddk"])
        hash_obj = SHA256.new(device_info["devicePhrase"].encode())
        signature = pkcs1_15.new(private_key).sign(hash_obj)
        x_signature = base64.b64encode(signature).decode("utf-8")

        download_info = self.session.post("https://marin-api.prd-prsn.com/api/1.0/capi/product",
                                          headers={"x-signature": x_signature},
                                          json={
                                              "entitlementSource": "RUMBA",
                                              "deviceId": self.device_id,
                                              "bookId": book_id
                                          }).json()
        if show_progress:
            download = self.session.get(download_info["packageUrl"],
                                        headers={"etext-cdn-token": download_info["cdnToken"]},stream=True)
            # Add a tqdm progress bar and save to variable
            total_size = int(download.headers.get('content-length', 0))
            downloaded_data = b""
            with tqdm(
                    desc="Downloading file...",
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
            ) as bar:
                for data in download.iter_content(chunk_size=8192):
                    bar.update(len(data))
                    downloaded_data += data

        else:
            download = self.session.get(download_info["packageUrl"],
                                        headers={"etext-cdn-token": download_info["cdnToken"]})
            downloaded_data = download.content
        private_key = decode_and_import_rsa_private_key(device_info["ddk"])
        decrypt = PKCS1_v1_5.new(private_key)
        key = decrypt.decrypt(base64.b64decode(download_info["securedKey"].encode()), None)
        pdf, iv = downloaded_data[16:], downloaded_data[:16]
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)


        with open(filename, "ab+") as decrypted_file:
            block_size = AES.block_size
            num_blocks = (len(pdf) + block_size - 1) // block_size
            with tqdm(
                    desc="Decrypting file...",
                    total=num_blocks,
                    unit='block',
                    unit_scale=True,
                    disable=not show_progress
            ) as bar:
                for i in range(0, len(pdf), block_size):
                    block = pdf[i:i + block_size]
                    decrypt_block = cipher.decrypt(block)
                    decrypted_file.write(decrypt_block)
                    bar.update(1)

