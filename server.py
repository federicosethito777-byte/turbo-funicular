import os

# Load .env file manually into os.environ if it exists (very robust fallback)
try:
    _dotenv_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(_dotenv_path):
        with open(_dotenv_path, 'r', encoding='utf-8') as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith('#'):
                    continue
                if '=' in _line:
                    _key, _val = _line.split('=', 1)
                    _key = _key.strip()
                    _val = _val.strip()
                    # Strip surrounding quotes if present
                    if (_val.startswith('"') and _val.endswith('"')) or (_val.startswith("'") and _val.endswith("'")):
                        _val = _val[1:-1]
                    if _key and _key not in os.environ:
                        os.environ[_key] = _val
except Exception as _e:
    print(f"[EnvLoader] Warning: Could not read .env file: {_e}")

# Diagnostic logging for NVIDIA API Key
_nvidia_present = 'YES' if (os.environ.get('NVIDIA_API') or os.environ.get('NVIDIA_API_KEY')) else 'NO'
print("\n" + "="*60)
print(f" [NVIDIA API KEY DIAGNOSTIC]: Available = {_nvidia_present}")
if _nvidia_present == 'YES':
    _key_val = os.environ.get('NVIDIA_API') or os.environ.get('NVIDIA_API_KEY')
    print(f" [NVIDIA API KEY SOURCE]: Found (Length: {len(_key_val)} chars, Starts with: {_key_val[:4]}...)")
else:
    print(" [NVIDIA API KEY SOURCE]: NOT found in system variables or .env file.")
print("="*60 + "\n")

import time
import uuid
import shutil
import threading
import requests
import base64
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pyngrok import ngrok
from playwright.sync_api import sync_playwright

app = Flask(__name__, static_folder='dist', static_url_path='')
CORS(app)

PORT = int(os.environ.get('PORT', 3000))
NGROK_AUTH_TOKEN = os.environ.get('NGROK_AUTH_TOKEN', '3Emryj9AYGhoUmWhs0XnHzcI7S0_5U6CyxVF2FzGJbmJFxb9d')

# Memory job store and locks
import json
JOBS_STORAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobs_storage.json')

jobs_lock = threading.Lock()
jobs = {}

def save_jobs_to_file():
    try:
        with jobs_lock:
            data_to_save = dict(jobs)
        with open(JOBS_STORAGE_PATH, 'w') as f:
            json.dump(data_to_save, f, indent=2)
    except Exception as e:
        print(f"[Jobs Storage] E: Could not persist jobs to disk: {e}")

def load_jobs_from_file():
    global jobs
    try:
        if os.path.exists(JOBS_STORAGE_PATH):
            with open(JOBS_STORAGE_PATH, 'r') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    with jobs_lock:
                        jobs.update(loaded)
                    print(f"[Jobs Storage] Successfully loaded {len(loaded)} jobs from {JOBS_STORAGE_PATH}")
    except Exception as e:
        print(f"[Jobs Storage] W: Could not load jobs from disk: {e}")

load_jobs_from_file()

ngrok_url = ""

# Ensure uploads directory
UPLOADS_DIR = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Proxy Cache system
proxy_cache = {
    'proxies': [],
    'last_updated': 0
}
proxy_cache_lock = threading.Lock()

def get_fresh_proxies():
    global proxy_cache
    now = time.time()
    # If we have proxies and they are less than 15 minutes old, return them
    with proxy_cache_lock:
        if proxy_cache['proxies'] and (now - proxy_cache['last_updated'] < 900):
            return list(proxy_cache['proxies'])

    print("[ProxyScraper] Fetching fresh HTTP proxies from public feeds...")
    sources = [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=8000&country=all&ssl=yes&anonymity=all",
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/officialputuid/tools/master/test.txt"
    ]
    
    parsed_proxies = []
    
    for url in sources:
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                lines = res.text.split('\n')
                for line in lines:
                    val = line.strip()
                    if val and ':' in val and not val.startswith('#'):
                        # validate format ip:port
                        parts = val.split(':')
                        if len(parts) == 2:
                            ip, port = parts[0], parts[1]
                            if port.isdigit():
                                parsed_proxies.append(val)
        except Exception as e:
            print(f"[ProxyScraper] Warning: URL {url} fetch error: {e}")
            
    # Deduplicate
    unique_proxies = list(set(parsed_proxies))
    print(f"[ProxyScraper] Parsed {len(unique_proxies)} unique public HTTP proxies.")
    
    with proxy_cache_lock:
        if unique_proxies:
            proxy_cache['proxies'] = unique_proxies
            proxy_cache['last_updated'] = now
            return unique_proxies
        else:
            return list(proxy_cache['proxies'])

def check_premium_limit(page):
    try:
        limit_detected = page.evaluate('''() => {
            try {
                const blockwords = [
                    "reached your limit",
                    "reached your daily limit",
                    "daily limit reach",
                    "limit reached",
                    "out of credits"
                ];
                
                const bodyText = document.body ? document.body.innerText : "";
                let foundWord = null;
                const lowerBody = bodyText.toLowerCase();
                for (const word of blockwords) {
                    if (lowerBody.includes(word)) {
                        foundWord = word;
                        break;
                    }
                }
                
                if (!foundWord) return null;
                
                const selectors = [
                    '.modal', '.popup', '[id*="modal"]', '[id*="popup"]',
                    '[class*="modal"]', '[class*="popup"]', '.active', '.show',
                    'div[style*="fixed"]', 'div[style*="absolute"]', '.techwave_fn_backdrop'
                ];
                
                for (const selector of selectors) {
                    try {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            if (el.offsetHeight > 0 && el.offsetWidth > 0) {
                                // Exclude standard static components and FAQs/sections
                                if (el.closest('header, nav, footer, .header, .nav, .footer, .menu, .sidebar, #header, #footer, #sidebar, #navbar, .faq, .accordion, .question, .answer, .presets, .presets-row, .tips, .tips-container, .feedback')) {
                                    continue;
                                }
                                
                                const elText = (el.textContent || '').toLowerCase();
                                if (elText.includes("frequently asked") || elText.includes("how it works") || elText.includes("example presets") || elText.includes("preguntas frecuentes")) {
                                    continue; // Skip static documentation / landing text
                                }
                                
                                if (elText.includes(foundWord)) {
                                    // Ensure it's not a standalone flat static text tag without a popover context
                                    if (el.tagName === 'P' || el.tagName === 'SPAN' || el.tagName === 'LI' || el.tagName === 'A') {
                                        const parentModal = el.closest('.modal, .popup, [id*="modal"], [id*="popup"], [class*="modal"], [class*="popup"], .techwave_fn_backdrop, div[style*="fixed"], div[style*="absolute"]');
                                        if (!parentModal) {
                                            continue; // ignore static flat text paragraphs
                                        }
                                    }
                                    
                                    return {
                                        detected: true,
                                        keyword: foundWord,
                                        selector: selector,
                                        tagName: el.tagName,
                                        className: el.className || "",
                                        id: el.id || "",
                                        textSnippet: elText.substring(0, 150)
                                    };
                                }
                            }
                        }
                    } catch(e) {}
                }
            } catch(err) {}
            return null;
        }''')
        return limit_detected
    except Exception as e:
        print(f"[CheckPremiumLimit] Error: {e}")
        return None

def check_and_raise_premium_limit(page):
    info = check_premium_limit(page)
    if info and info.get('detected'):
        raise Exception(f"PaymentLimitPopup: matched '{info.get('keyword')}' inside <{info.get('tagName')} id='{info.get('id')}' class='{info.get('className')}' selector='{info.get('selector')}'>. Snippet: {info.get('textSnippet')}")

import concurrent.futures

def test_single_proxy(proxy_addr):
    try:
        proxies = {
            "http": f"http://{proxy_addr}",
            "https": f"http://{proxy_addr}"
        }
        r = requests.get("https://veoaifree.com/", proxies=proxies, timeout=2.0)
        if r.status_code == 200:
            return proxy_addr
    except Exception:
        pass
    return None

def get_working_proxy_fast():
    proxies_list = get_fresh_proxies()
    if not proxies_list:
        return None
        
    import random
    candidates = list(proxies_list)
    random.shuffle(candidates)
    
    test_batch = candidates[:15]
    print(f"[ProxyTester] Testing {len(test_batch)} proxies concurrently...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(test_single_proxy, paddr): paddr for paddr in test_batch}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=3.0):
                res = future.result()
                if res:
                    print(f"[ProxyTester] Found active proxy: {res}")
                    return res
        except Exception as exc:
            print(f"[ProxyTester] Error inside as_completed: {exc}")
            
    print("[ProxyTester] No verified working proxies available. Falling back to Direct Connection.")
    return None

def update_job_progress(job_id, progress_text, status=None):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]['progress'] = progress_text
            if status:
                jobs[job_id]['status'] = status
    save_jobs_to_file()

def capture_job_screenshot(page, job_id):
    now = time.time()
    with jobs_lock:
        if job_id not in jobs:
            return
        last_time = jobs[job_id].get('last_screenshot_time', 0)
        # Cap screenshots to run at most once every 12 seconds
        if now - last_time < 12:
            return
        # Book the screenshot immediately so we don't start concurrent screenshots
        jobs[job_id]['last_screenshot_time'] = now

    try:
        shot_filename = f"shot-{job_id}-{int(now * 1000)}.png"
        shot_path = os.path.join(UPLOADS_DIR, shot_filename)
        print(f"[Screenshot] Capturing page state for job {job_id} after 12s interval...")
        page.screenshot(path=shot_path, type="png")
        with jobs_lock:
            if job_id in jobs:
                if 'screenshots' not in jobs[job_id]:
                    jobs[job_id]['screenshots'] = []
                jobs[job_id]['screenshots'].append(f'/uploads/{shot_filename}')
                # Write back finalized completion time
                jobs[job_id]['last_screenshot_time'] = time.time()
        save_jobs_to_file()
    except Exception as e:
        print(f"[Screenshot] Error capturing screenshot for job {job_id}: {e}")

def clean_old_jobs():
    # Keep jobs persistent for up to 7 days (7 * 24 * 3600 * 1000 ms)
    max_age_ms = 7 * 24 * 3600 * 1000
    now_ms = time.time() * 1000
    with jobs_lock:
        to_delete = []
        for jid, job in list(jobs.items()):
            if now_ms - job['createdAt'] > max_age_ms:
                if job.get('videoUrl'):
                    filename = os.path.basename(job['videoUrl'])
                    filepath = os.path.join(UPLOADS_DIR, filename)
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                        except Exception:
                            pass
                if job.get('screenshots'):
                    for shot_url in job['screenshots']:
                        filename = os.path.basename(shot_url)
                        filepath = os.path.join(UPLOADS_DIR, filename)
                        if os.path.exists(filepath):
                            try:
                                os.remove(filepath)
                            except Exception:
                                pass
                to_delete.append(jid)
        for jid in to_delete:
            jobs.pop(jid, None)
    if to_delete:
        save_jobs_to_file()

def download_file(src_url, dest_path):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    r = requests.get(src_url, headers=headers, stream=True)
    if r.status_code != 200:
        raise Exception(f"Failed to download video, HTTP {r.status_code}")
    with open(dest_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

def dismiss_popup_if_needed(page):
    try:
        # Run highly optimized DOM-cleaning script
        page.evaluate('''() => {
            try {
                const bodyText = document.body ? document.body.innerText : "";
                const premiumWords = [
                    "Unlock Premium Access", 
                    "Select Your Plan", 
                    "Get Monthly", 
                    "Get 3 Months", 
                    "Get Yearly", 
                    "Best Value", 
                    "Choose a pricing plan",
                    "pricing plan",
                    "Unlimited Video Generation"
                ];
                
                let hasPremium = false;
                for (const word of premiumWords) {
                    if (bodyText.includes(word)) {
                        hasPremium = true;
                        break;
                    }
                }
                
                if (hasPremium) {
                    const selectors = [
                        '.modal', '.popup', '[id*="modal"]', '[id*="popup"]',
                        '[class*="modal"]', '[class*="popup"]', '[class*="paywall"]',
                        '[class*="pricing"]', '.active', '.show',
                        'div[style*="fixed"]', 'div[style*="absolute"]'
                    ];
                    
                    selectors.forEach(selector => {
                        try {
                            const elements = document.querySelectorAll(selector);
                            elements.forEach(el => {
                                if (el === document.body || el === document.documentElement) return;
                                if (el.offsetHeight > 0) {
                                    const text = el.innerText || "";
                                    let matched = false;
                                    for (const word of premiumWords) {
                                        if (text.includes(word)) {
                                            matched = true;
                                            break;
                                        }
                                    }
                                    if (matched) {
                                        console.log("[PopupDismiss] Removing overlay container:", el);
                                        el.remove();
                                    }
                                }
                            });
                        } catch(e) {}
                    });
                }
                
                // Click standard close elements in remaining DOM
                const closeSelectors = [
                    '.fn_close', '.close', '.close-btn', '.close-button',
                    'button[aria-label="Close"]', 'button[aria-label="close"]',
                    '.techwave_fn_modal_close', '.popup_close'
                ];
                closeSelectors.forEach(sel => {
                    try {
                        document.querySelectorAll(sel).forEach(el => {
                            if (el.offsetHeight > 0) {
                                console.log("[PopupDismiss] Clicking close element:", sel);
                                el.click();
                            }
                        });
                    } catch(e) {}
                });
                
                // Click '×' or 'x' indicators in close-like elements
                try {
                    document.querySelectorAll('.close, [class*="close"]').forEach(el => {
                        if (el.offsetHeight > 0) {
                            const txt = (el.textContent || '').trim();
                            if (txt === '×' || txt === 'x' || txt === 'X') {
                                el.click();
                            }
                        }
                    });
                } catch(e) {}
                
                // Remove backdrops
                const backdrops = [
                    '.modal-backdrop', '.techwave_fn_backdrop', '.backdrop', '[class*="backdrop"]'
                ];
                backdrops.forEach(sel => {
                    try {
                        document.querySelectorAll(sel).forEach(el => {
                            el.remove();
                        });
                    } catch(e) {}
                });
                
                // Restore page scrolling and interaction
                document.body.style.overflow = 'auto';
                document.body.style.position = 'static';
                document.documentElement.style.overflow = 'auto';
            } catch(err) {
                console.error("[PopupDismiss] Inner script error:", err);
            }
        }''')
    except Exception as e:
        print(f"[PopupDismiss] Error trying to dismiss popup: {e}")

def handle_crop_modal(page, job_id, aspect_select=None):
    # Wait up to 10 seconds for crop modal to show up to account for potential slower proxy/renders
    update_job_progress(job_id, 'Waiting for potential post-upload modal to appear...')
    active_modal_selector = None
    for _ in range(20):
        try:
            active_modal_selector = page.evaluate('''() => {
                const selectors = ['#cropModal', '.modal', '.popup', '[class*="modal"]', '[id*="modal"]', '[role="dialog"]'];
                for (const sel of selectors) {
                    const elements = document.querySelectorAll(sel);
                    for (const el of elements) {
                        const style = window.getComputedStyle(el);
                        // Check if it's visible and actually contains some content
                        if (style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 50) {
                            // If it's a generic class modal, we might need a more specific way to target it
                            return sel; 
                        }
                    }
                }
                return null;
            }''')
            if active_modal_selector:
                break
        except Exception:
            pass
        time.sleep(0.5)

    if active_modal_selector:
        update_job_progress(job_id, f'Modal detected via {active_modal_selector}. Adjusting and auto-confirming...')
        
        # 1. Set aspect ratio if provided and present
        if aspect_select:
            try:
                for sel in ['#aspectSelect', '#aspect-ratio-select', '#crop-aspect', '#modal-aspect']:
                    if page.locator(sel).count() > 0:
                        try:
                            page.select_option(sel, aspect_select, timeout=1000)
                            update_job_progress(job_id, f"Aspect ratio set inside modal: {aspect_select}")
                            break
                        except Exception:
                            page.evaluate('([s, v]) => { const el = document.querySelector(s); if(el) { el.value = v; el.dispatchEvent(new Event("change", { bubbles: true })); } }', [sel, aspect_select])
                            update_job_progress(job_id, f"Aspect ratio set inside modal via fallback: {aspect_select}")
                            break
            except Exception as e:
                print(f"[Modal] Error setting aspect select: {e}")

        # Let's inspect buttons inside the detected modal
        try:
            buttons_info = page.evaluate('''(sel) => {
                const modal = document.querySelector(sel);
                if (!modal) return [];
                return Array.from(modal.querySelectorAll('button, a, input[type="button"], [role="button"], span, div')).map(el => {
                    const text = el.innerText ? el.innerText.trim() : (el.value ? el.value.trim() : '');
                    const textLower = text.toLowerCase();
                    const idLower = el.id ? el.id.toLowerCase() : '';
                    const clsLower = el.className ? el.className.toLowerCase() : '';
                    const isCandidate = textLower.includes('crop') || textLower.includes('confirm') || textLower.includes('ok') || textLower.includes('apply') || textLower.includes('save') || textLower.includes('done') || idLower.includes('crop') || clsLower.includes('crop') || idLower.includes('confirm') || clsLower.includes('confirm');
                    if (!isCandidate && el.tagName !== 'BUTTON' && el.tagName !== 'A') return null;
                    return {
                        id: el.id,
                        tagName: el.tagName,
                        className: el.className,
                        text: text,
                        visible: el.offsetWidth > 0 || el.offsetHeight > 0 || window.getComputedStyle(el).display !== 'none'
                    };
                }).filter(Boolean);
            }''', active_modal_selector)
            print(f"[Modal] Found buttons: {buttons_info}")
            
            # Look for button with text "Crop", "Confirm", "OK", "Apply", "Save", "Cut", "Done" or class containing "crop" or ID containing "crop"
            target_button_selector = None
            
            # First try finding any visible button whose text or ID has "crop"
            for btn in buttons_info:
                text_lower = btn['text'].lower()
                id_lower = btn['id'].lower() if btn['id'] else ''
                cls_lower = btn['className'].lower() if btn['className'] else ''
                if btn['visible']:
                    if 'crop' in text_lower or 'crop' in id_lower or 'crop' in cls_lower:
                        if btn['id']:
                            target_button_selector = f"#{btn['id']}"
                            break
                        elif btn['className']:
                            # Safe split to build classes
                            classes = ".".join([c for c in btn['className'].split() if c and ":" not in c])
                            if classes:
                                target_button_selector = f"button.{classes}, a.{classes}, div.{classes}, span.{classes}"
                                break
            
            # Second try: any button containing upload, confirm, apply, save, ok, done, choose, select
            if not target_button_selector:
                # Prioritize #upload-btn as mentioned by the user
                for btn in buttons_info:
                    if btn['id'] == 'upload-btn' and btn['visible']:
                        target_button_selector = '#upload-btn'
                        break
                
                if not target_button_selector:
                    for btn in buttons_info:
                        text_lower = btn['text'].lower()
                        if btn['visible'] and any(word in text_lower for word in ['upload', 'confirm', 'apply', 'save', 'ok', 'done', 'choose', 'select']):
                            if btn['id']:
                                target_button_selector = f"#{btn['id']}"
                                break
                            elif btn['className']:
                                classes = ".".join([c for c in btn['className'].split() if c and ":" not in c])
                                if classes:
                                    target_button_selector = f"button.{classes}, a.{classes}, div.{classes}, span.{classes}"
                                    break
                        
            # Third try: click by text or ID like #cropBtn or #upload-btn
            if not target_button_selector:
                try:
                    if page.locator('#upload-btn').count() > 0:
                        target_button_selector = '#upload-btn'
                    elif page.locator('#cropBtn').count() > 0:
                        target_button_selector = '#cropBtn'
                    elif page.locator('#crop_it').count() > 0:
                        target_button_selector = '#crop_it'
                except Exception:
                    pass
                    
            # Fourth try: if there's any visible button that isn't typically "cancel" or "close"
            if not target_button_selector:
                for btn in buttons_info:
                    text_lower = btn['text'].lower()
                    if btn['visible'] and not any(word in text_lower for word in ['cancel', 'close', 'dismiss', 'x']):
                        if btn['id']:
                            target_button_selector = f"#{btn['id']}"
                            break
            
            if target_button_selector:
                update_job_progress(job_id, f"Clicking crop confirmation button: {target_button_selector}")
                try:
                    page.locator(target_button_selector).first.click(force=True, timeout=5000)
                except Exception as click_err:
                    print(f"[CropModal] Playwright locator click failed: {click_err}. Trying standard page.click force-mode.")
                    try:
                        page.click(target_button_selector, force=True, timeout=3000)
                    except Exception:
                        pass
            else:
                # Let's try executing JavaScript click as fallback on any promising element
                clicked_via_js = page.evaluate('''(sel) => {
                    const modal = document.querySelector(sel);
                    if (!modal) return false;
                    const btns = Array.from(modal.querySelectorAll('button, a, input[type="button"], div, span'));
                    // Look for best match
                    let target = btns.find(b => {
                        const txt = (b.innerText || b.value || '').toLowerCase();
                        return txt.includes('crop') || b.id.toLowerCase().includes('crop') || b.className.toLowerCase().includes('crop');
                    });
                    if (!target) {
                        target = btns.find(b => {
                            const txt = (b.innerText || b.value || '').toLowerCase();
                            return txt.includes('confirm') || txt.includes('apply') || txt.includes('save') || txt.includes('done');
                        });
                    }
                    if (!target && btns.length > 0) {
                        // Use any non-cancel buttton
                        target = btns.find(b => {
                            const txt = (b.innerText || b.value || '').toLowerCase();
                            return !txt.includes('cancel') && !txt.includes('close');
                        });
                    }
                    if (target) {
                        target.click();
                        return true;
                    }
                    return false;
                }''', active_modal_selector)
                update_job_progress(job_id, f"Fallback JS confirmation button click status: {clicked_via_js}")
                
            # Wait up to 5 seconds for the modal to close/disappear with active click retries
            modal_still_open = True
            for attempt in range(12):
                still_open = page.evaluate('''(sel) => {
                    const modal = document.querySelector(sel);
                    if (modal) {
                        const style = window.getComputedStyle(modal);
                        return style.display !== 'none' && style.visibility !== 'hidden' && modal.offsetHeight > 50;
                    }
                    return false;
                }''', active_modal_selector)
                if not still_open:
                    update_job_progress(job_id, 'Modal closed successfully.')
                    modal_still_open = False
                    break
                
                # Active re-clicks if modal is taking too long
                if attempt > 2 and target_button_selector:
                    print(f"[Modal] Still open (attempt {attempt}). Re-clicking selector: {target_button_selector}")
                    try:
                        page.locator(target_button_selector).first.click(force=True, timeout=2000)
                    except Exception:
                        pass
                elif attempt > 2:
                    print(f"[Modal] Still open (attempt {attempt}). Re-clicking via JS...")
                    page.evaluate('''(sel) => {
                        const modal = document.querySelector(sel);
                        if (!modal) return;
                        const btns = Array.from(modal.querySelectorAll('button, a, input[type="button"], div, span'));
                        let target = btns.find(b => {
                            const txt = (b.innerText || b.value || '').toLowerCase();
                            return txt.includes('crop') || b.id.toLowerCase().includes('crop') || b.className.toLowerCase().includes('crop');
                        });
                        if (!target) {
                            target = btns.find(b => {
                                const txt = (b.innerText || b.value || '').toLowerCase();
                                return txt.includes('confirm') || txt.includes('apply') || txt.includes('save') || txt.includes('done');
                            });
                        }
                        if (target) {
                            target.click();
                        }
                    }''', active_modal_selector)
                time.sleep(0.5)

            # Ultimate safe fallback: If modal is still open, forcefully close it to prevent blocking pointer events
            if modal_still_open:
                update_job_progress(job_id, 'Modal remains open. Force shielding backdrop and hiding modal...')
                page.evaluate('''(sel) => {
                    try {
                        const modal = document.querySelector(sel);
                        if (modal) {
                            // Click confirmation button one more time via JS
                            const btns = Array.from(modal.querySelectorAll('button, a, input[type="button"], div, span'));
                            let btn = btns.find(b => {
                                const t = (b.innerText || b.value || '').toLowerCase();
                                return t.includes('crop') || t.includes('confirm') || t.includes('cut') || t.includes('ok') || t.includes('apply');
                            });
                            if (btn) {
                                btn.click();
                            }
                            // Force-hide modal from layout/rendering
                            modal.classList.remove('show');
                            modal.style.display = 'none';
                            modal.setAttribute('aria-hidden', 'true');
                        }
                        // Remove overlay backdrops that might intercept events
                        document.querySelectorAll('.modal-backdrop, .overlay, .modal-backdrop-bg, .cropper-modal').forEach(el => {
                            el.remove();
                        });
                        // Restore body and container overflow & touch/pointer states
                        document.body.classList.remove('modal-open');
                        document.body.style.overflow = 'auto';
                        document.body.style.position = 'static';
                        document.body.style.pointerEvents = 'auto';
                        
                        document.documentElement.style.overflow = 'auto';
                        document.documentElement.style.pointerEvents = 'auto';
                    } catch(e) {
                        console.error("[Modal Force Close Error]:", e);
                    }
                }''', active_modal_selector)
                time.sleep(1)

        except Exception as crop_err:
            print(f"[CropModal] Button matching/clicking error: {crop_err}")
    else:
        update_job_progress(job_id, 'No crop modal detected, continuing normal process.')

def run_text_to_video_job(job_id, model, aspect_ratio, prompt):
    # Try up to 5 smart attempts (4 distinct validated proxies + direct connection fallback)
    update_job_progress(job_id, 'Validating and selecting ultra-fast active proxy...', status='processing')
    
    proxies_to_try = []
    # Fetch distinct proxies
    for _ in range(4):
        p = get_working_proxy_fast()
        if p and p not in proxies_to_try:
            proxies_to_try.append(p)
            
    proxies_to_try.append(None) # Always fallback to direct connection
    
    last_error = None
    successful = False
    
    for attempt, use_proxy in enumerate(proxies_to_try):
        try:
            with sync_playwright() as p:
                browser = None
                try:
                    # Configure launch options
                    launch_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
                    launch_opts = {
                        "headless": True,
                        "args": launch_args
                    }
                    if use_proxy:
                        launch_opts["proxy"] = {"server": f"http://{use_proxy}"}
                        update_job_progress(job_id, f"Launching with proxy {use_proxy} (Attempt {attempt + 1}/{len(proxies_to_try)})...", status='processing')
                    else:
                        update_job_progress(job_id, f"Launching via server direct connection (Fallback Attempt {attempt + 1}/{len(proxies_to_try)})...", status='processing')
                        
                    browser = p.chromium.launch(**launch_opts)
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    page = context.new_page()
                    
                    update_job_progress(job_id, 'Navigating to Grok Video Generator...')
                    page.goto('https://veoaifree.com/grok-ai-video-generator/', timeout=60000, wait_until='domcontentloaded')
                    
                    check_and_raise_premium_limit(page)
                        
                    dismiss_popup_if_needed(page)

                    update_job_progress(job_id, 'Opening advanced settings...')
                    paths = page.locator('path').all()
                    settings_clicked = False
                    for path_loc in paths:
                        try:
                            d = path_loc.get_attribute('d')
                            if d and 'M408.6,364.9c-21.4' in d.replace(' ', ''):
                                try:
                                    path_loc.click(force=True, timeout=5000)
                                except Exception:
                                    path_loc.locator('xpath=..').click(force=True, timeout=5000)
                                settings_clicked = True
                                break
                        except Exception:
                            pass

                    if not settings_clicked:
                        try:
                            page.locator('.techwave_fn_button').first.click(force=True, timeout=5000)
                        except Exception:
                            pass

                    dismiss_popup_if_needed(page)
                    update_job_progress(job_id, 'Setting model and aspect ratios...')
                    try:
                        page.wait_for_selector('#modal', state='attached', timeout=10000)
                    except Exception:
                        pass
                    try:
                        page.select_option('#modal', model, timeout=500)
                    except Exception:
                        page.evaluate('([sel, val]) => { const el = document.querySelector(sel); if(el) { el.value = val; el.dispatchEvent(new Event("change", { bubbles: true })); } }', ['#modal', model])

                    try:
                        page.wait_for_selector('#aspect-ration', state='attached', timeout=5000)
                    except Exception:
                        pass
                    try:
                        page.select_option('#aspect-ration', aspect_ratio, timeout=500)
                    except Exception:
                        page.evaluate('([sel, val]) => { const el = document.querySelector(sel); if(el) { el.value = val; el.dispatchEvent(new Event("change", { bubbles: true })); } }', ['#aspect-ration', aspect_ratio])

                    update_job_progress(job_id, 'Inputting prompt text...')
                    page.wait_for_selector('#fn__include_textarea', timeout=5000)
                    page.fill('#fn__include_textarea', prompt)

                    # Gather initial pre-rendered videos
                    initial_videos = set()
                    try:
                        video_urls = page.evaluate('''() => {
                            const list = [];
                            const videoExts = ['.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'];
                            const isVideoUrl = (url) => {
                                if (!url) return false;
                                const lUrl = url.toLowerCase();
                                if (lUrl.includes('logo') || lUrl.includes('avatar') || lUrl.includes('preview') || lUrl.includes('tutorial')) {
                                    return false;
                                }
                                if (lUrl.startsWith('blob:')) return true;
                                return videoExts.some(ext => lUrl.includes(ext));
                            };
                            document.querySelectorAll('video').forEach((el) => {
                                if (el.src && isVideoUrl(el.src)) list.push(el.src);
                            });
                            document.querySelectorAll('source').forEach((el) => {
                                if (el.src && isVideoUrl(el.src)) list.push(el.src);
                            });
                            document.querySelectorAll('a').forEach((el) => {
                                if (el.href && isVideoUrl(el.href)) {
                                    list.push(el.href);
                                }
                            });
                            return list;
                        }''')
                        initial_videos.update(video_urls)
                    except Exception as e:
                        print("Error getting initial videos:", e)

                    dismiss_popup_if_needed(page)
                    update_job_progress(job_id, 'Submitting prompt for rendering...')
                    page.wait_for_selector('#generate_it', timeout=5000)
                    page.click('#generate_it')

                    # Wait slightly and check if the daily limit / payment modal immediately appeared
                    time.sleep(2)
                    check_and_raise_premium_limit(page)

                    update_job_progress(job_id, 'Rendering video (can take 1-2 minutes). Please wait...')

                    video_url = None
                    start_time = time.time()
                    timeout_seconds = 180 # 3 mins

                    while time.time() - start_time < timeout_seconds:
                        dismiss_popup_if_needed(page)
                        check_and_raise_premium_limit(page)
                        capture_job_screenshot(page, job_id)
                        try:
                            current_urls = page.evaluate('''() => {
                                const results = [];
                                const videoExts = ['.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'];
                                const isVideoUrl = (url) => {
                                    if (!url) return false;
                                    const lUrl = url.toLowerCase();
                                    if (lUrl.includes('logo') || lUrl.includes('avatar') || lUrl.includes('preview') || lUrl.includes('tutorial')) {
                                        return false;
                                    }
                                    if (lUrl.startsWith('blob:')) return true;
                                    return videoExts.some(ext => lUrl.includes(ext));
                                };
                                document.querySelectorAll('video').forEach((v) => {
                                    if (v.src && isVideoUrl(v.src)) results.push(v.src);
                                });
                                document.querySelectorAll('source').forEach((s) => {
                                    if (s.src && isVideoUrl(s.src)) results.push(s.src);
                                });
                                document.querySelectorAll('a').forEach((a) => {
                                    if (a.href && isVideoUrl(a.href)) {
                                        results.push(a.href);
                                    }
                                });
                                return results;
                            }''')
                            
                            new_url = next((url for url in current_urls if url not in initial_videos), None)
                            if new_url:
                                video_url = new_url
                                break
                        except Exception as eval_err:
                            print("Error checking for rendering video:", eval_err)

                        time.sleep(5)

                    if not video_url:
                        raise Exception('Video generation timed out or could not retrieve URL from DOM.')

                    update_job_progress(job_id, 'Finalizing video link...')
                    with jobs_lock:
                        if job_id in jobs:
                            jobs[job_id]['status'] = 'completed'
                            jobs[job_id]['progress'] = 'Completed'
                            jobs[job_id]['videoUrl'] = video_url
                    save_jobs_to_file()
                    
                    successful = True
                    break # Success! Break proxies loop

                finally:
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass
        except Exception as err:
            print(f"[TextToVideo Proxy Attempt {attempt + 1} Failed]: {err}")
            last_error = err
            if "PaymentLimitPopup" in str(err):
                update_job_progress(job_id, f"Daily limit or paywall active on proxy: {use_proxy or 'Direct Connection'}. Scanning/Rotating proxies...")
            else:
                update_job_progress(job_id, f"Connection timeout or selector error with proxy: {use_proxy or 'Direct Connection'}. Trying next proxy...")
                
    if not successful:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]['status'] = 'failed'
                jobs[job_id]['progress'] = 'Failed'
                jobs[job_id]['error'] = f"Grok video generation failed after trying all available clean proxies. Reason: {last_error}"
        save_jobs_to_file()

def run_image_to_video_job(job_id, model, aspect_ratio, aspect_select, vertical_pos, horizontal_pos, prompt, image_path):
    # Try validated fast proxies first to avoid rate-limiting and paywalls on Server IP, fallback to direct last
    update_job_progress(job_id, 'Validating and selecting ultra-fast active proxy...', status='processing')
    
    modes_to_try = []
    # Fetch distinct proxies
    for _ in range(4):
        p = get_working_proxy_fast()
        if p and p not in [item[1] for item in modes_to_try if item[1] is not None]:
            modes_to_try.append((f"Active Proxy: {p}", p))
            
    modes_to_try.append(("Direct Connection Fallback", None)) # Fallback to direct last
            
    last_error = None
    successful = False
    
    for attempt, (mode_name, use_proxy) in enumerate(modes_to_try):
        try:
            with sync_playwright() as p:
                browser = None
                try:
                    update_job_progress(job_id, f"Launching browser via {mode_name}...", status='processing')
                    launch_opts = {
                        "headless": True,
                        "args": ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
                    }
                    if use_proxy:
                        launch_opts["proxy"] = {"server": f"http://{use_proxy}"}
                        
                    browser = p.chromium.launch(**launch_opts)
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    page = context.new_page()
                    
                    update_job_progress(job_id, 'Navigating to Photo-to-Video Generator...')
                    page.goto('https://veoaifree.com/photo-and-image-to-video-generator/', timeout=60000, wait_until='domcontentloaded')
                    
                    check_and_raise_premium_limit(page)
                        
                    run_image_to_video_job_guts(page, job_id, model, aspect_ratio, aspect_select, vertical_pos, horizontal_pos, prompt, image_path)
                    
                    successful = True
                    break # Success! Break retry loop

                finally:
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass
        except Exception as err:
            print(f"[ImageToVideo {mode_name} Attempt Failed]: {err}")
            last_error = err
            if "PaymentLimitPopup" in str(err):
                update_job_progress(job_id, f"Daily limit or paywall active via {mode_name}. Scanning and rotating proxies to fallback...")
            else:
                update_job_progress(job_id, f"Connection timeout or selector error via {mode_name}. Rotating proxies to fallback...")

    if not successful:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]['status'] = 'failed'
                jobs[job_id]['progress'] = 'Failed'
                jobs[job_id]['error'] = f"Grok image-to-video generation failed. Reason: {last_error}"
        save_jobs_to_file()

    # Clean up uploaded image
    if os.path.exists(image_path):
        try:
            os.remove(image_path)
        except Exception:
            pass

def run_image_to_video_job_guts(page, job_id, model, aspect_ratio, aspect_select, vertical_pos, horizontal_pos, prompt, image_path):
    dismiss_popup_if_needed(page)

    update_job_progress(job_id, 'Opening advanced settings...')
    paths = page.locator('path').all()
    settings_clicked = False
    for path_loc in paths:
        try:
            d = path_loc.get_attribute('d')
            if d and 'M408.6,364.9c-21.4' in d.replace(' ', ''):
                try:
                    path_loc.click(force=True, timeout=5000)
                except Exception:
                    path_loc.locator('xpath=..').click(force=True, timeout=5000)
                settings_clicked = True
                break
        except Exception:
            pass

    if not settings_clicked:
        try:
            page.locator('.techwave_fn_button').first.click(force=True, timeout=5000)
        except Exception:
            pass

    capture_job_screenshot(page, job_id)
    dismiss_popup_if_needed(page)
    update_job_progress(job_id, 'Setting selectors and model...')
    try:
        page.wait_for_selector('#modal', state='attached', timeout=10000)
    except Exception:
        pass
    try:
        page.select_option('#modal', model, timeout=500)
    except Exception:
        page.evaluate('([sel, val]) => { const el = document.querySelector(sel); if(el) { el.value = val; el.dispatchEvent(new Event("change", { bubbles: true })); } }', ['#modal', model])

    # Select aspect ratio (with fallback to #aspect-ration)
    aspect_ratio_selector = '#aspect-ration-img-video'
    try:
        page.wait_for_selector(aspect_ratio_selector, state='attached', timeout=3000)
    except Exception:
        aspect_ratio_selector = '#aspect-ration'
        try:
            page.wait_for_selector(aspect_ratio_selector, state='attached', timeout=3000)
        except Exception:
            aspect_ratio_selector = None

    if aspect_ratio_selector:
        update_job_progress(job_id, f"Setting aspect ratio using selector {aspect_ratio_selector}...")
        try:
            page.select_option(aspect_ratio_selector, aspect_ratio, timeout=1000)
        except Exception:
            page.evaluate('([sel, val]) => { const el = document.querySelector(sel); if(el) { el.value = val; el.dispatchEvent(new Event("change", { bubbles: true })); } }', [aspect_ratio_selector, aspect_ratio])

    capture_job_screenshot(page, job_id)
    
    # Log page info for debugging
    page_info = page.evaluate('''() => ({
        title: document.title,
        url: window.location.href,
        fileInputs: document.querySelectorAll('input[type="file"]').length,
        bodyText: (document.body ? document.body.innerText.substring(0, 500) : ''),
    })''')
    print(f"[Upload Debug] Page info: {json.dumps(page_info, indent=2)}")
    
    update_job_progress(job_id, 'Uploading image...')

    # Verify the image file exists
    if not os.path.exists(image_path):
        raise Exception(f"Image file not found at path: {image_path}")

    uploaded = False

    # Log what's actually on the page for debugging
    page_state = page.evaluate('''() => {
        const inputs = document.querySelectorAll('input[type="file"]');
        const visible_svgs = [];
        document.querySelectorAll('svg').forEach(s => {
            const cls = s.getAttribute('class') || '';
            if (cls.includes('image') || cls.includes('upload')) {
                visible_svgs.push(cls);
            }
        });
        return {
            fileInputCount: inputs.length,
            fileInputDetails: Array.from(inputs).map(i => ({
                id: i.id, name: i.name, className: i.className, hidden: i.hidden
            })),
            relatedSvgs: visible_svgs
        };
    }''')
    print(f"[Upload Debug] Page state: {page_state}")

    # Wait a bit for page to settle
    page.wait_for_timeout(1000)

    # Try set_input_files with force=True on all file inputs
    all_inputs = page.locator('input[type="file"]').all()
    print(f"[Upload Debug] Playwright found {len(all_inputs)} file inputs")
    
    # Prioritize inputs that are visible or have 'image' in their accept attribute
    file_inputs = []
    for inp in all_inputs:
        try:
            is_visible = inp.is_visible()
            accept = inp.get_attribute('accept') or ''
            if is_visible or 'image' in accept.lower():
                file_inputs.insert(0, inp)
            else:
                file_inputs.append(inp)
        except:
            file_inputs.append(inp)

    for i, inp in enumerate(file_inputs):
        try:
            inp.set_input_files(image_path, timeout=10000, force=True)
            uploaded = True
            update_job_progress(job_id, f"Image uploaded via direct file input #{i}")
            page.wait_for_timeout(2000) # Give UI time to react
            break
        except Exception as e:
            print(f"Direct set_input_files on input #{i} failed: {e}")

    # Fallback: click elements that trigger file chooser
    if not uploaded:
        for upload_selector in [
            '#upload-btn',
            '.upload-trigger',
            '.plus-icon-container',
            '.img-attach-cont',
            '.img-1-cont',
            '.plus-attach-img',
            '.attach-images',
            '[data-target]',
            '.upload-btn',
            '#image-upload-btn',
            'button:has-text("Upload")',
            'label:has-text("Upload")',
        ]:
            try:
                btn = page.locator(upload_selector).first
                count = btn.count()
                print(f"[Upload Debug] Selector '{upload_selector}': count={count}")
                if count > 0:
                    with page.expect_file_chooser(timeout=10000) as fc_info:
                        btn.click(timeout=5000, force=True)
                    file_chooser = fc_info.value
                    file_chooser.set_files(image_path)
                    uploaded = True
                    update_job_progress(job_id, f"Image uploaded via clicking {upload_selector}")
                    page.wait_for_timeout(2000)
                    break
            except Exception as e:
                print(f"Upload via selector '{upload_selector}' failed: {e}")

    # Fallback: use JS to programmatically set the file
    if not uploaded:
        try:
            import base64
            with open(image_path, 'rb') as f:
                b64_data = base64.b64encode(f.read()).decode('utf-8')
            ext = os.path.splitext(image_path)[1].lower()
            mime = 'image/png' if ext == '.png' else 'image/jpeg'
            file_name = os.path.basename(image_path)

            js_result = page.evaluate('''({b64, mime, name}) => {
                try {
                    const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
                    if (inputs.length === 0) return "no-inputs";
                    
                    // Try to find the best input
                    const inp = inputs.find(i => i.accept && i.accept.includes('image')) || inputs[0];
                    
                    const byteStr = atob(b64);
                    const ab = new ArrayBuffer(byteStr.length);
                    const ia = new Uint8Array(ab);
                    for (let i = 0; i < byteStr.length; i++) {
                        ia[i] = byteStr.charCodeAt(i);
                    }
                    const blob = new Blob([ab], {type: mime});
                    const file = new File([blob], name, {type: mime});
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    
                    // Use native setter for React/Vue compatibility
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'files'
                    ).set;
                    
                    // Try setting it for all inputs as a shotgun approach if we are desperate
                    inputs.forEach(input => {
                        try {
                            nativeInputValueSetter.call(input, dt.files);
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('blur', { bubbles: true }));
                        } catch(e) {}
                    });
                    
                    return "ok";
                } catch(e) { return "error: " + e.message; }
            }''', {'b64': b64_data, 'mime': mime, 'name': file_name})

            if js_result == "ok":
                uploaded = True
                update_job_progress(job_id, "Image uploaded via JS")
                page.wait_for_timeout(2000)
            else:
                print(f"JS upload returned: {js_result}")
        except Exception as e:
            print(f"JS upload failed: {e}")
            import traceback
            traceback.print_exc()

    if not uploaded:
        raise Exception("Image upload failed: could not set file on any input or trigger file chooser")

    capture_job_screenshot(page, job_id)

    # Detect and handle potential crop modal (which contains #aspectSelect) after file is uploaded
    handle_crop_modal(page, job_id, aspect_select)

    update_job_progress(job_id, 'Inputting prompt text...')
    # Select prompt textarea with multiple fallbacks
    prompt_selector = None
    for ps in ['#fn__include_textarea_img_video', '#fn__include_textarea', 'textarea[placeholder*="Enter prompt"]', 'textarea#prompt', '.prompt-input', 'textarea']:
        try:
            if page.locator(ps).count() > 0:
                page.wait_for_selector(ps, timeout=3000)
                prompt_selector = ps
                break
        except Exception:
            pass

    if prompt_selector:
        update_job_progress(job_id, f"Inputting prompt text using selector {prompt_selector}...")
        page.fill(prompt_selector, prompt)
    else:
        # Fallback to any visible textarea
        update_job_progress(job_id, "Searching for any available textarea to input prompt...")
        try:
            page.locator('textarea').first.fill(prompt)
        except Exception as e:
            print(f"Failed to fill fallback textarea: {e}")

    capture_job_screenshot(page, job_id)

    # Filter existing pre-rendered videos
    initial_videos = set()
    try:
        video_urls = page.evaluate('''() => {
            const list = [];
            const videoExts = ['.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'];
            const isVideoUrl = (url) => {
                if (!url) return false;
                const lUrl = url.toLowerCase();
                if (lUrl.includes('logo') || lUrl.includes('avatar') || lUrl.includes('preview') || lUrl.includes('tutorial')) {
                    return false;
                }
                if (lUrl.startsWith('blob:')) return true;
                return videoExts.some(ext => lUrl.includes(ext));
            };
            document.querySelectorAll('video').forEach((el) => {
                if (el.src && isVideoUrl(el.src)) list.push(el.src);
            });
            document.querySelectorAll('source').forEach((el) => {
                if (el.src && isVideoUrl(el.src)) list.push(el.src);
            });
            document.querySelectorAll('a').forEach((el) => {
                if (el.href && isVideoUrl(el.href)) {
                    list.push(el.href);
                }
            });
            return list;
        }''')
        initial_videos.update(video_urls)
    except Exception as e:
        print("Error getting initial videos:", e)

    dismiss_popup_if_needed(page)
    update_job_progress(job_id, 'Submitting specifications for rendering...')
    # Select generate button with multiple fallbacks
    generate_selector = None
    for gs in ['#generate_it_img_video', '#generate_it', 'button:has-text("Generate")', 'button#generate-btn', 'button:has-text("Generate Video")', '.generate-btn', '#generate_btn']:
        try:
            if page.locator(gs).count() > 0:
                page.wait_for_selector(gs, timeout=3000)
                generate_selector = gs
                break
        except Exception:
            pass

    if generate_selector:
        update_job_progress(job_id, f"Submitting specifications using selector {generate_selector}...")
        # Wait up to 5 seconds for the generate button to be visible
        try:
            page.locator(generate_selector).first.wait_for(state='visible', timeout=5000)
        except Exception:
            pass
            
        # Ensure any disabled attributes are removed as fallback and trigger click
        try:
            # Force click with Playwright first
            page.locator(generate_selector).first.click(force=True, timeout=5000)
            print("[Generate] Successfully clicked generate button via Playwright force-click.")
        except Exception as e:
            print(f"[Generate] Playwright click on {generate_selector} failed: {e}. Trying JS click.")
            try:
                page.evaluate(f'''() => {{
                    const btn = document.querySelector("{generate_selector}");
                    if (btn) {{
                        btn.removeAttribute('disabled');
                        btn.classList.remove('disabled');
                        btn.click();
                    }}
                }}''')
            except Exception as js_err:
                print(f"[Generate] Fallback JS click on {generate_selector} failed: {js_err}")
    else:
        # Fallback click on submit/button containing "Generate"
        update_job_progress(job_id, "Attempting to locate generate button via alternative selectors...")
        try:
            get_btn = page.locator('input[type="submit"], button:has-text("Generate"), button[id*="generate"]').first
            try:
                get_btn.wait_for(state='visible', timeout=3000)
            except Exception:
                pass
                
            # Perform force/JS click as fallback
            try:
                get_btn.click(force=True, timeout=5000)
            except Exception:
                page.evaluate('''() => {
                    const btn = Array.from(document.querySelectorAll('input[type="submit"], button')).find(b => {
                        const txt = (b.innerText || b.value || '').toLowerCase();
                        return txt.includes('generate') || b.id.includes('generate');
                    });
                    if (btn) {
                        btn.removeAttribute('disabled');
                        btn.classList.remove('disabled');
                        btn.click();
                    }
                }''')
        except Exception as e:
            print(f"Failed to click fallback generate button: {e}")

    # Wait slightly and check if the daily limit / payment modal immediately appeared
    time.sleep(2)
    capture_job_screenshot(page, job_id)
    check_and_raise_premium_limit(page)

    update_job_progress(job_id, 'Rendering video (can take 1-2 minutes). Please wait...')

    video_url = None
    start_time = time.time()
    timeout_seconds = 180

    while time.time() - start_time < timeout_seconds:
        dismiss_popup_if_needed(page)
        check_and_raise_premium_limit(page)
        capture_job_screenshot(page, job_id)
        try:
            current_urls = page.evaluate('''() => {
                const results = [];
                const videoExts = ['.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'];
                const isVideoUrl = (url) => {
                    if (!url) return false;
                    const lUrl = url.toLowerCase();
                    if (lUrl.includes('logo') || lUrl.includes('avatar') || lUrl.includes('preview') || lUrl.includes('tutorial')) {
                        return false;
                    }
                    if (lUrl.startsWith('blob:')) return true;
                    return videoExts.some(ext => lUrl.includes(ext));
                };
                document.querySelectorAll('video').forEach((v) => {
                    if (v.src && isVideoUrl(v.src)) results.push(v.src);
                });
                document.querySelectorAll('source').forEach((s) => {
                    if (s.src && isVideoUrl(s.src)) results.push(s.src);
                });
                document.querySelectorAll('a').forEach((a) => {
                    if (a.href && isVideoUrl(a.href)) {
                        results.push(a.href);
                    }
                });
                return results;
            }''')
            
            new_url = next((url for url in current_urls if url not in initial_videos), None)
            if new_url:
                video_url = new_url
                break
        except Exception as eval_err:
            print("Error checking for image rendering video:", eval_err)

        time.sleep(5)

    if not video_url:
        raise Exception('Video generation timed out or could not retrieve URL from DOM.')

    update_job_progress(job_id, 'Finalizing video link...')
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['progress'] = 'Completed'
            jobs[job_id]['videoUrl'] = video_url
    save_jobs_to_file()

# ---- API Routes ----

@app.route('/api/generate-prompt', methods=['POST'])
def generate_prompt():
    data = request.json or {}
    user_prompt = data.get('prompt', '')
    if not user_prompt:
        return jsonify({'error': 'Prompt text is required'}), 400

    nvidia_api_key = os.environ.get('NVIDIA_API') or os.environ.get('NVIDIA_API_KEY')
    if not nvidia_api_key:
        return jsonify({
            'error': 'NVIDIA_API key is missing. Please configure NVIDIA_API (or NVIDIA_API_KEY) in your environment or .env file to run the Maverick visual prompt generator.'
        }), 400

    try:
        headers = {
            "Authorization": f"Bearer {nvidia_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "meta/llama-4-maverick-17b-128e-instruct",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a prompt engineering expert for AI video generation. Rewrite/optimize the user's input into a highly cinematic, descriptive video prompt of 1-3 sentences. Output ONLY the polished prompt without any extra text, packaging, introduction, or explanations.",
                },
                {
                    "role": "user",
                    "content": f"Optimize this concept: {user_prompt}"
                }
            ],
            "temperature": 0.5,
            "max_tokens": 200
        }
        
        response = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=15
        )
        
        if response.status_code != 200:
            return jsonify({'error': f"NVIDIA NIM API Error {response.status_code}: {response.text}"}), 502
            
        res_data = response.json()
        enhanced_prompt = res_data['choices'][0]['message']['content'].strip()
        # strip any wrapping quotes
        if (enhanced_prompt.startswith('"') and enhanced_prompt.endswith('"')) or (enhanced_prompt.startswith("'") and enhanced_prompt.endswith("'")):
            enhanced_prompt = enhanced_prompt[1:-1]
            
        return jsonify({'enhancedPrompt': enhanced_prompt})
    except Exception as e:
        return jsonify({'error': f"Failed to connect to NVIDIA NIM generator: {str(e)}"}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        'status': 'ok',
        'ngrokUrl': ngrok_url if ngrok_url else 'Tunneling initialization...',
        'ngrokEnabled': bool(ngrok_url)
    })

@app.route('/api/generate-video', methods=['POST'])
def generate_video():
    data = request.json or {}
    model = data.get('model', '3.1')
    aspect_ratio = data.get('aspectRatio', 'VIDEO_ASPECT_RATIO_PORTRAIT')
    prompt = data.get('prompt')

    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400

    clean_old_jobs()

    job_id = f"txt-{int(time.time() * 1000) % 1000000}"
    new_job = {
        'id': job_id,
        'type': 'text-to-video',
        'status': 'queued',
        'progress': 'Queued',
        'videoUrl': None,
        'error': None,
        'screenshots': [],
        'createdAt': time.time() * 1000
    }

    with jobs_lock:
        jobs[job_id] = new_job
    save_jobs_to_file()

    # Start thread
    t = threading.Thread(target=run_text_to_video_job, args=(job_id, model, aspect_ratio, prompt))
    t.start()

    return jsonify({'jobId': job_id, 'status': 'queued'})

@app.route('/api/generate-img-to-video', methods=['POST'])
def generate_img_to_video():
    clean_old_jobs()

    # Support JSON requests (ideal for Custom GPTs and clients sending Base64 or URLs directly)
    if request.is_json:
        data = request.json or {}
        prompt = data.get('prompt')
        model = data.get('model', '3.1')
        aspect_ratio = data.get('aspectRatio', 'VIDEO_ASPECT_RATIO_PORTRAIT')
        aspect_select = data.get('aspectSelect', 'vertical')
        vertical_pos = data.get('verticalPos', '')
        horizontal_pos = data.get('horizontalPos', '')
        image_data = data.get('imageData') or data.get('image_data') or data.get('image_url') or data.get('imageUrl')

        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        if not image_data:
            return jsonify({'error': 'Image data (imageData / base64 or imageUrl / public URL) is required'}), 400

        try:
            unique_name = f"input-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            image_path = None

            if image_data.startswith("data:"):
                # Handle Base64 Data URI
                try:
                    header, base64_data = image_data.split(",", 1)
                except ValueError:
                    return jsonify({'error': 'Invalid base64 Data URI format. Missing comma separator.'}), 400

                ext = ".png"
                if "image/jpeg" in header or "image/jpg" in header:
                    ext = ".jpg"
                elif "image/webp" in header:
                    ext = ".webp"
                elif "image/gif" in header:
                    ext = ".gif"

                file_bytes = base64.b64decode(base64_data)
                image_path = os.path.join(UPLOADS_DIR, f"{unique_name}{ext}")
                with open(image_path, 'wb') as f:
                    f.write(file_bytes)
            elif not image_data.startswith("http://") and not image_data.startswith("https://") and len(image_data) > 100:
                # Handle raw base64 string
                file_bytes = base64.b64decode(image_data)
                ext = ".png"
                if file_bytes.startswith(b'\xff\xd8\xff'):
                    ext = ".jpg"
                elif file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    ext = ".png"
                elif file_bytes.startswith(b'RIFF') and b'WEBP' in file_bytes[:12]:
                    ext = ".webp"

                image_path = os.path.join(UPLOADS_DIR, f"{unique_name}{ext}")
                with open(image_path, 'wb') as f:
                    f.write(file_bytes)
            else:
                # Handle HTTP(S) url
                resp = requests.get(image_data, timeout=30)
                if resp.status_code != 200:
                    return jsonify({'error': f'Failed to fetch image from URL, status code: {resp.status_code}'}), 400

                ext = ".png"
                content_type = resp.headers.get('content-type', '').lower()
                if 'jpeg' in content_type or 'jpg' in content_type:
                    ext = ".jpg"
                elif 'webp' in content_type:
                    ext = ".webp"
                elif 'gif' in content_type:
                    ext = ".gif"

                image_path = os.path.join(UPLOADS_DIR, f"{unique_name}{ext}")
                with open(image_path, 'wb') as f:
                    f.write(resp.content)

        except Exception as e:
            return jsonify({'error': f'Failed to process or decode image input. Details: {str(e)}'}), 400

    else:
        # Standard web multipart/form-data file upload (used by React app)
        prompt = request.form.get('prompt')
        model = request.form.get('model', '3.1')
        aspect_ratio = request.form.get('aspectRatio', 'VIDEO_ASPECT_RATIO_PORTRAIT')
        aspect_select = request.form.get('aspectSelect', 'vertical')
        vertical_pos = request.form.get('verticalPos', '')
        horizontal_pos = request.form.get('horizontalPos', '')
        file = request.files.get('image')

        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        if not file:
            return jsonify({'error': 'Image file upload is required'}), 400

        # Save uploaded file
        file_ext = os.path.splitext(file.filename)[1]
        unique_name = f"input-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}{file_ext}"
        image_path = os.path.join(UPLOADS_DIR, unique_name)
        file.save(image_path)

    job_id = f"img-{int(time.time() * 1000) % 1000000}"
    new_job = {
        'id': job_id,
        'type': 'image-to-video',
        'status': 'queued',
        'progress': 'Queued',
        'videoUrl': None,
        'error': None,
        'screenshots': [],
        'createdAt': time.time() * 1000
    }

    with jobs_lock:
        jobs[job_id] = new_job
    save_jobs_to_file()

    # Start thread to drive Chrome/Playwright container and complete the render
    t = threading.Thread(target=run_image_to_video_job, args=(job_id, model, aspect_ratio, aspect_select, vertical_pos, horizontal_pos, prompt, image_path))
    t.start()

    return jsonify({'jobId': job_id, 'status': 'queued'})

@app.route('/api/job-status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/uploads/<path:filename>', methods=['GET'])
def serve_uploads(filename):
    import re
    from flask import Response
    filepath = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    # Support range requests for HTML5 video elements (very important for Safari/Chrome/iOS)
    file_size = os.path.getsize(filepath)
    range_header = request.headers.get('Range', None)

    if not range_header:
        # Standard whole-file response has conditional=True
        return send_from_directory(UPLOADS_DIR, filename)

    # Decode Range format: "bytes=123-456" or "bytes=123-"
    byte1, byte2 = None, None
    match = re.search(r'bytes=(\d+)-(\d*)', range_header)
    if match:
        groups = match.groups()
        if groups[0]:
            byte1 = int(groups[0])
        if groups[1]:
            byte2 = int(groups[1])

    start = byte1 if byte1 is not None else 0
    end = byte2 if byte2 is not None else file_size - 1

    if start >= file_size:
        return "Requested Range Not Satisfiable", 416

    end = min(end, file_size - 1)
    length = end - start + 1

    def generate_chunks():
        with open(filepath, 'rb') as f:
            f.seek(start)
            remaining = length
            chunk_size = 1024 * 64
            while remaining > 0:
                to_read = min(chunk_size, remaining)
                data = f.read(to_read)
                if not data:
                    break
                yield data
                remaining -= len(data)

    resp = Response(generate_chunks(), 206, mimetype='video/mp4', direct_passthrough=True)
    resp.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
    resp.headers.add('Accept-Ranges', 'bytes')
    resp.headers.add('Content-Length', str(length))
    return resp

# ---- Model Context Protocol (MCP) Server ----

import queue
import json

mcp_sessions = {}
mcp_sessions_lock = threading.Lock()

def handle_mcp_message(data):
    if not isinstance(data, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"}
        }
        
    msg_id = data.get("id")
    method = data.get("method")
    params = data.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "BautiAI-MCP-Server",
                    "version": "1.0.0"
                }
            }
        }
        
    elif method == "notifications/initialized":
        return None
        
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": "generate_video",
                        "description": "Starts a background headless browser pipeline to generate a video from a text prompt using BautiAI (VeoAIFree/Grok automation). Returns the started job ID which you can check progress on.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "prompt": {
                                    "type": "string",
                                    "description": "High-fidelity, descriptive prompt detailing what should appear in the video."
                                },
                                "model": {
                                    "type": "string",
                                    "description": "Select model option to use (default: '3.1'). Options include: '3.1', '3.0', 'veo-2'."
                                },
                                "aspect_ratio": {
                                    "type": "string",
                                    "description": "Aspect ratio of video. Options: 'portrait', 'landscape' (default: 'portrait')."
                                }
                            },
                            "required": ["prompt"]
                        }
                    },
                    {
                        "name": "get_job_status",
                        "description": "Track progress logs, screenshot events, and download files for any active or past job ID.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "job_id": {
                                    "type": "string",
                                    "description": "The unique job ID returned by the generator."
                                }
                            },
                            "required": ["job_id"]
                        }
                    },
                    {
                        "name": "get_jobs_list",
                        "description": "List all active, queued, or completed jobs on this server with their current status, timestamps, and files.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                ]
            }
        }
        
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        if tool_name == "generate_video":
            prompt = args.get("prompt")
            model = args.get("model", "3.1")
            ratio_alias = args.get("aspect_ratio", "portrait").lower()
            
            # Map friendly aliases
            aspect_ratio = "VIDEO_ASPECT_RATIO_PORTRAIT"
            if "landscape" in ratio_alias:
                aspect_ratio = "VIDEO_ASPECT_RATIO_LANDSCAPE"
                
            if not prompt:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32602, "message": "Missing 'prompt' argument"}
                }
                
            clean_old_jobs()
            job_id = f"txt-mcp-{int(time.time() * 1000) % 1000000}"
            new_job = {
                'id': job_id,
                'type': 'text-to-video',
                'status': 'queued',
                'progress': 'Queued via MCP Server API',
                'videoUrl': None,
                'error': None,
                'screenshots': [],
                'createdAt': time.time() * 1000
            }
            with jobs_lock:
                jobs[job_id] = new_job
            save_jobs_to_file()
            
            # Start thread
            t = threading.Thread(target=run_text_to_video_job, args=(job_id, model, aspect_ratio, prompt))
            t.start()
            
            # Form response
            text_response = (
                f"Successfully started text-to-video job via BautiAI MCP.\n"
                f"Job ID: {job_id}\n"
                f"Model: {model}\n"
                f"Aspect ratio: {aspect_ratio}\n"
                f"Prompt: {prompt}\n\n"
                f"You can now track this job's progress in real-time or check status by calling 'get_job_status' with job_id='{job_id}'."
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": text_response
                        }
                    ]
                }
            }
            
        elif tool_name == "generate_image_to_video":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "The 'generate_image_to_video' tool is temporarily disabled from Custom GPTs/MCP to avoid security blocks on image transfer. Please use the BautiAI Web App to generate videos starting from images."
                        }
                    ],
                    "isError": True
                }
            }
            
        elif tool_name == "get_job_status":
            target_id = args.get("job_id")
            if not target_id:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32602, "message": "Missing 'job_id' parameter"}
                }
                
            with jobs_lock:
                job = jobs.get(target_id)
                
            if not job:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Job not found for ID: {target_id}. It might have expired or has not been created."
                            }
                        ],
                        "isError": True
                    }
                }
                
            # Construct host or tunnel URL for screenshots/urls
            base_url = ngrok_url if ngrok_url else request.host_url.rstrip('/')
            
            # Build nice readable output
            video_url_display = "Not available yet"
            if job.get('videoUrl'):
                if job['videoUrl'].startswith('http'):
                    video_url_display = job['videoUrl']
                else:
                    video_url_display = f"{base_url}{job['videoUrl']}"
                    
            screenshots_str = ""
            if job.get('screenshots'):
                shots = []
                for shot in job['screenshots']:
                    if shot.startswith('http'):
                        shots.append(shot)
                    else:
                        shots.append(f"{base_url}{shot}")
                screenshots_str = "\n".join([f"- {s}" for s in shots])
            else:
                screenshots_str = "None captured yet"
                
            text_response = (
                f"--- Job Status Report ---\n"
                f"Job ID: {job.get('id')}\n"
                f"Type: {job.get('type')}\n"
                f"Status: {job.get('status').upper()}\n"
                f"Live Progress Log: {job.get('progress')}\n"
                f"Video Delivery Link: {video_url_display}\n"
                f"Error details: {job.get('error') or 'None'}\n"
                f"State Screenshots:\n{screenshots_str}"
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": text_response
                        }
                    ]
                }
            }
            
        elif tool_name == "get_jobs_list":
            with jobs_lock:
                all_jobs = list(jobs.values())
                
            # Build nice summary
            if not all_jobs:
                summary = "Zero active or past video generation jobs currently stored on this server."
            else:
                summary = f"Total jobs: {len(all_jobs)}\n\n"
                for i, j in enumerate(all_jobs):
                    summary += (
                        f"{i+1}. ID: {j.get('id')} | Type: {j.get('type')} | Status: {j.get('status')} "
                        f"| Progress: {j.get('progress')[:40]}...\n"
                    )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": summary
                        }
                    ]
                }
            }
            
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Tool '{tool_name}' not found."}
            }
            
    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": "Method not found"}
        }

@app.route('/api/mcp/sse', methods=['GET'])
def mcp_sse():
    import queue
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    q = queue.Queue()
    
    with mcp_sessions_lock:
        mcp_sessions[session_id] = q
        
    def event_generator():
        # Send an absolute URL to avoid issues with some LLM clients resolving relative paths
        base_url = ngrok_url if ngrok_url else request.url_root.rstrip('/')
        endpoint_url = f"{base_url}/api/mcp/messages?session_id={session_id}"
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"
        
        print(f"[MCP SSE] Session {session_id} connected.")
        try:
            while True:
                try:
                    # Retrieve the next JSON-RPC response with timeout to allow ping/keepalive
                    msg = q.get(timeout=30.0)
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                except queue.Empty:
                    # SSE keep-alive comment
                    yield ": ping\n\n"
        except GeneratorExit:
            print(f"[MCP SSE] Session {session_id} disconnected.")
        finally:
            with mcp_sessions_lock:
                mcp_sessions.pop(session_id, None)

    # Return stream
    from flask import Response
    return Response(event_generator(), content_type='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    })

@app.route('/api/mcp/messages', methods=['POST'])
def mcp_messages():
    session_id = request.args.get('session_id')
    data = request.json or {}
    
    # Process message
    response = handle_mcp_message(data)
    
    if not response:
        # e.g., notifications don't return responses
        return '', 202
        
    if session_id:
        with mcp_sessions_lock:
            q = mcp_sessions.get(session_id)
        if q:
            # Push response to the client's SSE stream!
            q.put(response)
            return '', 200
            
    # Default direct HTTP fallback if no session exists or session disconnected
    return jsonify(response)

# ---- Client React Router & Static Assets Fallback ----

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    # Prevent directory traversal attacks and sanitize path
    cleaned_path = os.path.normpath(path).replace('..', '') if path else ""
    full_path = os.path.join(app.static_folder, cleaned_path)
    
    # Check if this requested path is a static asset (has common extension or in assets/)
    is_asset_path = cleaned_path.startswith('assets/') or any(
        cleaned_path.lower().endswith(ext) for ext in ['.css', '.js', '.mjs', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif', '.ico', '.woff', '.woff2', '.json', '.map']
    )
    
    # If it is an asset but the file does not exist, return a proper 404 instead of index.html
    if is_asset_path and not os.path.exists(full_path):
        print(f"[Static Serve] [404] Missing asset file: {cleaned_path}")
        return "Asset not found", 404
        
    # If path is not empty and file exists inside dist, serve it
    if cleaned_path != "" and os.path.exists(full_path):
        mimetype = None
        lower_path = cleaned_path.lower()
        if lower_path.endswith('.css'):
            mimetype = 'text/css'
        elif lower_path.endswith('.js') or lower_path.endswith('.mjs'):
            mimetype = 'application/javascript'
        elif lower_path.endswith('.svg'):
            mimetype = 'image/svg+xml'
        elif lower_path.endswith('.png'):
            mimetype = 'image/png'
        elif lower_path.endswith('.jpg') or lower_path.endswith('.jpeg'):
            mimetype = 'image/jpeg'
        elif lower_path.endswith('.webp'):
            mimetype = 'image/webp'
        elif lower_path.endswith('.gif'):
            mimetype = 'image/gif'
        elif lower_path.endswith('.ico'):
            mimetype = 'image/x-icon'
        elif lower_path.endswith('.json'):
            mimetype = 'application/json'
        elif lower_path.endswith('.woff2'):
            mimetype = 'font/woff2'
        elif lower_path.endswith('.woff'):
            mimetype = 'font/woff'
            
        print(f"[Static Serve] Path: {cleaned_path} -> MIME: {mimetype if mimetype else 'Auto'}")
        return send_from_directory(app.static_folder, cleaned_path, mimetype=mimetype)
    else:
        # Otherwise serve index.html for SPA router functionality
        print(f"[Static Serve] Fallback index.html for Path: {cleaned_path}")
        return send_from_directory(app.static_folder, 'index.html')

# ---- Ngrok initialization ----

def start_ngrok():
    global ngrok_url
    try:
        print("[Ngrok] Setting up tunnel...")

        # 1. Kill any existing local system-wide lingering ngrok processes first
        import subprocess
        for proc_cmd in [["pkill", "-9", "-f", "ngrok"], ["killall", "-9", "ngrok"]]:
            try:
                subprocess.run(proc_cmd, capture_output=True, timeout=5)
                print(f"[Ngrok] Executed process kill command: {' '.join(proc_cmd)}")
            except Exception:
                pass

        # 2. Query local ngrok API on port 4040 if active, and disconnect any existing tunnels
        try:
            import requests
            resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                for tun in data.get("tunnels", []):
                    name = tun.get("name")
                    if name:
                        requests.delete(f"http://127.0.0.1:4040/api/tunnels/{name}", timeout=3)
                        print(f"[Ngrok] Proactively disconnected active tunnel via Local API: {name}")
        except Exception:
            pass

        ngrok.set_auth_token(NGROK_AUTH_TOKEN)
        
        # Kill previous lingering tunnels within the pyngrok context safely
        try:
            ngrok.kill()
        except Exception:
            pass
            
        print("[Ngrok] Connecting new tunnel...")
        # 3. Establish tunnel with pooling enabled fallback to optimize safe concurrent runs
        try:
            tunnel = ngrok.connect(PORT, proto='http', pooling_enabled=True)
            print("[Ngrok] Successfully created tunnel with pooling_enabled=True")
        except Exception as pool_err:
            print(f"[Ngrok] Pooling fallback note: {pool_err}. Retrying without pooling...")
            tunnel = ngrok.connect(PORT, proto='http')
            
        ngrok_url = tunnel.public_url
        print("\n\n" + "="*80)
        print(" [NGROK INFRASTRUCTURE DETECTED]")
        print(f" [NGROK PUBLIC TUNNEL URL]: {ngrok_url}")
        print(" [STATUS]: ACTIVE & ONLINE")
        print("="*80 + "\n\n")
    except Exception as e:
        print(f"[Ngrok] Could not establish tunnel (non-blocking): {e}")

if __name__ == '__main__':
    # Start ngrok in background thread to prevent blocking fast startup of web server
    t = threading.Thread(target=start_ngrok)
    t.start()
    
    print(f"Python web server listening at http://0.0.0.0:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
