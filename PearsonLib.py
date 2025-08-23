import base64
import random
import re
import shutil
import string
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional, List
from tempfile import TemporaryDirectory
import requests
import fitz
from lxml import etree as et
from playwright.sync_api import sync_playwright
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Util.Padding import unpad
from tqdm import tqdm


CLIENT_ID = "t1txmB9oRay3yK5aIQxsS28Z9T19xMLM"
DEVICE_ID_LENGTH = 16
DOWNLOADS_DIR = "pearson_downloads"

class PearsonError(Exception):
    pass


class CryptoUtils:
    @staticmethod
    def decode_and_import_rsa_private_key(data: str) -> RSA.RsaKey:
        try:
            private_key_bytes = base64.b64decode(base64.b64decode(data.encode()))
            return RSA.import_key(private_key_bytes)
        except Exception as e:
            raise PearsonError(f"Failed to decode RSA private key: {e}")

    @staticmethod
    def decrypt_aes_data(data: bytes, key: bytes) -> bytes:
        try:
            iv, ciphertext = data[:16], data[16:]
            cipher = AES.new(key, AES.MODE_CBC, iv=iv)
            return unpad(cipher.decrypt(ciphertext), AES.block_size)
        except Exception as e:
            raise PearsonError(f"Failed to decrypt AES data: {e}")


class FileProcessor:
    @staticmethod
    def decrypt_bin_files_in_folder(folder_path: Path, aes_key: bytes, remove_bin: bool = True) -> None:
        for path in folder_path.rglob("*.bin"):
            try:
                data = path.read_bytes()
                decrypted = CryptoUtils.decrypt_aes_data(data, aes_key)
                
                new_path = path.with_suffix('')
                new_path.write_bytes(decrypted)
                
                if remove_bin:
                    path.unlink()
            except Exception as e:
                print(f"Failed to decrypt {path}: {e}")

    @staticmethod
    def epub_to_pdf(epub_file: Path, output_pdf: Path, margin="1cm", scale=0.7):
        pdf = fitz.Document()
        toc, labels, pages = [], [], []

        with TemporaryDirectory(prefix="epub2pdf.") as tmpdir:
            tmpdir = Path(tmpdir)

            # Extract EPUB
            with zipfile.ZipFile(epub_file, "r") as zf:
                zf.extractall(tmpdir)

            # Locate container.xml
            container_path = tmpdir / "META-INF" / "container.xml"
            container = et.parse(container_path).getroot()
            rootfile_path = tmpdir / container.find("{*}rootfiles").find("{*}rootfile").get("full-path")

            # Parse OPF
            opf = et.parse(rootfile_path).getroot()
            manifest = {item.get("id"): item.get("href") for item in opf.find("{*}manifest").findall("{*}item")}
            spine = opf.find("{*}spine")
            pages = [(rootfile_path.parent / manifest[item.get("idref")]).resolve() for item in spine.findall("{*}itemref")]

            # Parse NAV for TOC
            nav_path = None
            for _, href in manifest.items():
                if href.endswith(("nav.xhtml", "nav.html")):
                    nav_path = rootfile_path.parent / href
                    break
                if href.endswith("toc.ncx"):
                    nav_path = rootfile_path.parent / href
                    break

            if nav_path is None:
                pass  # No TOC found, just continue without it
            elif nav_path.suffix == ".ncx":
                # Parse NCX TOC
                ncx_tree = et.parse(nav_path).getroot()
                for navpoint in ncx_tree.findall(".//{*}navPoint"):
                    title = navpoint.find(".//{*}text").text
                    src = navpoint.find(".//{*}content").get("src").split("#")[0]
                    href = (nav_path.parent / src).resolve()
                    if href in pages:
                        toc.append([1, title.strip(), pages.index(href) + 1])
            else:
                # Parse NAV (EPUB 3)
                nav_tree = et.parse(nav_path).getroot()
                toc_nav = next(
                    i for i in nav_tree.find("{*}body").findall("{*}nav")
                    if i.get("{http://www.idpf.org/2007/ops}type") == "toc"
                )

                def parse_nav(ol, level=1):
                    for li in ol.findall("{*}li"):
                        a = li.find("{*}a")
                        if a is None:
                            continue
                        href = (nav_path.parent / a.get("href").split("#")[0]).resolve()
                        title = (a.text or "").strip()
                        if href in pages:
                            toc.append([level, title, pages.index(href) + 1])
                        sub = li.find("{*}ol")
                        if sub is not None:
                            parse_nav(sub, level + 1)

                parse_nav(toc_nav.find("{*}ol"))

            # Render pages with Playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                for idx, page_path in enumerate(pages):
                    page.goto(page_path.as_uri())
                    size_match = re.search(r'content.+?width\s*=\s*([0-9]+).+?height\s*=\s*([0-9]+)',
                                           page_path.read_text(encoding="utf-8"), re.S)
                    width = str(int(size_match.group(1)) / 144) + "in" if size_match else "8.27in"
                    height = str(int(size_match.group(2)) / 144) + "in" if size_match else "11.69in"
                    pdf_bytes = page.pdf(print_background=True, width=width, height=height,
                                         margin={"top": margin, "bottom": margin, "left": "0", "right": "0"}, scale=scale)
                    page_pdf = fitz.Document(stream=pdf_bytes, filetype="pdf")
                    pdf.insert_pdf(page_pdf)
                    labels.append(str(idx + 1))
                browser.close()

        pdf.set_toc(toc)
        pdf.save(output_pdf)

class Pearson:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, downloads_dir: str = DOWNLOADS_DIR):
        self.session = requests.Session()
        self.device_id = self._generate_device_id()
        self.access_token: Optional[str] = None
        self.username = username
        self.password = password
        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(exist_ok=True)

    def _generate_device_id(self) -> str:
        return ''.join(random.choice(string.ascii_letters + string.digits) 
                      for _ in range(DEVICE_ID_LENGTH))

    def _get_user_agent(self) -> str:
        device_info = {
            "browser": "Android Device",
            "device": "Phone", 
            "display": "Custom",
            "id": self.device_id,
            "os": "Android"
        }
        return f"mobile_app|{device_info}"

    def login(self) -> bool:
        if not self.username or not self.password:
            raise PearsonError("Username and password are required")

        headers = {"User-Agent": self._get_user_agent()}
        data = {
            "password": self.password,
            "username": self.username,
            "isMobile": "true",
            "grant_type": "password",
            "client_id": CLIENT_ID
        }

        try:
            response = self.session.post("https://login.pearson.com/v1/piapi/login/webcredentials", headers=headers, data=data)
            response.raise_for_status()
            
            response_data = response.json()
            self.access_token = response_data.get("data", {}).get("access_token")
            
            if self.access_token:
                self.session.headers["Authorization"] = f"Bearer {self.access_token}"
                return True
            else:
                raise PearsonError("No access token received")
                
        except requests.RequestException as e:
            raise PearsonError(f"Login request failed: {e}")
        except KeyError as e:
            raise PearsonError(f"Unexpected response format: {e}")

    def get_bookshelf(self) -> List[Dict[str, Any]]:
        if not self.access_token:
            raise PearsonError("Not logged in. Call login() first.")

        try:
            response = self.session.get("https://marin-api.prd-prsn.com/api/1.0/bookshelf")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise PearsonError(f"Failed to get bookshelf: {e}")

    def _get_device_info(self) -> Dict[str, Any]:
        try:
            url = f"https://marin-api.prd-prsn.com/api/1.0/capi/ddk/device/{self.device_id}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise PearsonError(f"Failed to get device info: {e}")

    def _create_signature(self, device_phrase: str, signature_ddk: str) -> str:
        try:
            private_key = CryptoUtils.decode_and_import_rsa_private_key(signature_ddk)
            hash_obj = SHA256.new(device_phrase.encode())
            signature = pkcs1_15.new(private_key).sign(hash_obj)
            return base64.b64encode(signature).decode("utf-8")
        except Exception as e:
            raise PearsonError(f"Failed to create signature: {e}")

    def _get_download_info(self, book_id: str, product_id: str, entitlement_source: str, x_signature: str) -> Dict[str, Any]:
        try:
            # Build request data based on entitlement source
            if entitlement_source == "RUMBA":
                request_data = {
                    "entitlementSource": entitlement_source,
                    "deviceId": self.device_id,
                    "bookId": book_id
                }
            else:  # PASSPORT or other
                request_data = {
                    "productId": product_id,
                    "entitlementSource": entitlement_source,
                    "deviceId": self.device_id,
                    "bookId": book_id
                }
            
            response = self.session.post(
                "https://marin-api.prd-prsn.com/api/1.0/capi/product",
                headers={"x-signature": x_signature},
                json=request_data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise PearsonError(f"Failed to get download info: {e}")

    def _download_file(self, url: str, cdn_token: str, show_progress: bool = False) -> bytes:
        try:
            headers = {"etext-cdn-token": cdn_token}
            response = self.session.get(url, headers=headers, stream=show_progress)
            response.raise_for_status()
            
            if show_progress:
                total_size = int(response.headers.get('content-length', 0))
                downloaded_data = b""
                
                with tqdm(
                    desc="Downloading file...",
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                ) as progress_bar:
                    for chunk in response.iter_content(chunk_size=8192):
                        progress_bar.update(len(chunk))
                        downloaded_data += chunk
                
                return downloaded_data
            else:
                return response.content
                
        except requests.RequestException as e:
            raise PearsonError(f"Failed to download file: {e}")

    def _process_epub_file(self, file_path: Path, aes_key: bytes, convert_to_pdf: bool = True) -> Path:
        extract_folder = file_path.parent / (file_path.stem + "_extracted")
        extract_folder.mkdir(exist_ok=True)
        
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(extract_folder)
            
            FileProcessor.decrypt_bin_files_in_folder(extract_folder, aes_key)
            
            if convert_to_pdf:
                # Create EPUB first
                epub_path = file_path.with_suffix(".epub")
                shutil.make_archive(str(extract_folder), 'zip', root_dir=extract_folder)
                zip_path = Path(str(extract_folder) + ".zip")
                zip_path.rename(epub_path)
                
                # Convert to PDF
                pdf_path = file_path.with_suffix(".pdf")
                FileProcessor.epub_to_pdf(epub_path, pdf_path)
                
                # Clean up
                shutil.rmtree(extract_folder)
                file_path.unlink(missing_ok=True)
                epub_path.unlink(missing_ok=True)  # Remove the temporary EPUB
                return pdf_path
            else:
                epub_path = file_path.with_suffix(".epub")
                shutil.make_archive(str(extract_folder), 'zip', root_dir=extract_folder)
                zip_path = Path(str(extract_folder) + ".zip")
                zip_path.rename(epub_path)
                
                shutil.rmtree(extract_folder)
                file_path.unlink(missing_ok=True)
                return epub_path
            
        except Exception as e:
            if extract_folder.exists():
                shutil.rmtree(extract_folder)
            raise PearsonError(f"Failed to process EPUB: {e}")

    def _process_pdf_file(self, file_path: Path, encrypted_data: bytes, aes_key: bytes) -> Path:
        try:
            decrypted_data = CryptoUtils.decrypt_aes_data(encrypted_data, aes_key)
            file_path.write_bytes(decrypted_data)
            return file_path
        except Exception as e:
            raise PearsonError(f"Failed to process PDF: {e}")

    def download_book(self, book_id: str, product_id: str, entitlement_source: str, filename: str, show_progress: bool = False) -> Path:
        if not self.access_token:
            raise PearsonError("Not logged in. Call login() first.")

        device_info = self._get_device_info()
        x_signature = self._create_signature(
            device_info["devicePhrase"], 
            device_info["signature-ddk"]
        )
        
        download_info = self._get_download_info(book_id, product_id, entitlement_source, x_signature)
        
        downloaded_data = self._download_file(
            download_info["packageUrl"],
            download_info["cdnToken"],
            show_progress
        )
        
        private_key = CryptoUtils.decode_and_import_rsa_private_key(device_info["ddk"])
        encrypted_key = base64.b64decode(download_info["securedKey"].encode())
        aes_key = PKCS1_v1_5.new(private_key).decrypt(encrypted_key, None)
        
        if aes_key is None:
            raise PearsonError("Failed to decrypt AES key")
        
        file_path = self.downloads_dir / filename
        file_path.write_bytes(downloaded_data)
        
        try:
            if zipfile.is_zipfile(file_path):
                return self._process_epub_file(file_path, aes_key, convert_to_pdf=True)
            else:
                return self._process_pdf_file(file_path, downloaded_data, aes_key)
        except Exception as e:
            if file_path.exists():
                file_path.unlink()
            raise e