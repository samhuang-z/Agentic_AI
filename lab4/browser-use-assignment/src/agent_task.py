#!/usr/bin/env python3
"""
PagePilot Agent Task - Modified to use Claude API via litellm
Task: Search for NCU CSIE on Google and find the department website
"""

import sys
import os
import platform
import time
import json
import re
import logging
import base64

# Add PagePilot to Python path
PAGEPILOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'PagePilot')
PAGEPILOT_DIR = os.path.abspath(PAGEPILOT_DIR)
sys.path.insert(0, PAGEPILOT_DIR)

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import litellm

from prompts import SYSTEM_PROMPT
from utils import get_web_element_rect, encode_image, extract_information, clip_message_and_obs

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TASK = {
    "id": "google-ncu-csie",
    "ques": (
        "Go to Google, search for 'National Central University Department of "
        "Computer Science and Information Engineering', and find the official "
        "department website URL. Then provide the URL as the answer."
    ),
    "web": "https://www.google.com/",
}

MODEL = "anthropic/claude-sonnet-4-6"  # via litellm
MAX_ITER = 10
MAX_ATTACHED_IMGS = 2
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def setup_driver(download_dir: str):
    options = webdriver.ChromeOptions()
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("disable-blink-features=AutomationControlled")
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "plugins.always_open_pdf_externally": True,
    })
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)
    return driver


def call_llm(messages: list) -> tuple:
    """Call Claude via litellm and return (prompt_tokens, completion_tokens, content)."""
    resp = litellm.completion(
        model=MODEL,
        messages=messages,
        max_tokens=1000,
    )
    pt = resp.usage.prompt_tokens
    ct = resp.usage.completion_tokens
    content = resp.choices[0].message.content
    return pt, ct, content


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # --- Output dirs ---
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    screenshot_dir = os.path.join(base_dir, "screenshots")
    download_dir = os.path.join(base_dir, "downloads")
    os.makedirs(screenshot_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)

    # --- Logging ---
    log_path = os.path.join(screenshot_dir, "agent.log")
    logging.basicConfig(
        filename=log_path, level=logging.INFO,
        format="%(asctime)s %(levelname)s - %(message)s",
        force=True,
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger().addHandler(console)

    task = TASK
    logging.info(f"Task: {task['ques']}")

    # --- Browser ---
    driver = setup_driver(download_dir)
    driver.get(task["web"])
    time.sleep(3)
    try:
        driver.find_element("tag name", "body").click()
    except Exception:
        pass
    driver.execute_script(
        'window.onkeydown = function(e) {'
        'if(e.keyCode == 32 && e.target.type != "text" && e.target.type != "textarea")'
        '{e.preventDefault();}};'
    )
    time.sleep(2)

    # --- Agent loop ---
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    obs_prompt = "Observation: please analyze the attached screenshot and give the Thought and Action. "
    init_msg = (
        f"Now given a task: {task['ques']}  "
        f"Please interact with {task['web']} and get the answer.\n{obs_prompt}"
    )

    total_prompt_tokens = 0
    total_completion_tokens = 0
    action_log = []
    timings = []
    fail_obs = ""
    warn_obs = ""
    rects = []

    for it in range(1, MAX_ITER + 1):
        iter_start = time.time()
        logging.info(f"========== Iteration {it} ==========")

        # --- Observation ---
        if not fail_obs:
            try:
                rects, web_eles, web_eles_text = get_web_element_rect(driver, fix_color=True)
            except Exception as e:
                logging.error(f"Element detection error: {e}")
                break

            img_path = os.path.join(screenshot_dir, f"screenshot{it}.png")
            driver.save_screenshot(img_path)
            b64_img = encode_image(img_path)

            visible_range = driver.execute_script(
                'const st=window.scrollY,sh=document.documentElement.scrollHeight-window.innerHeight;'
                'const s=(st/sh)*100,e=((st+window.innerHeight)/sh)*100;'
                'return `${s.toFixed(1)}%-${e.toFixed(1)}%`;'
            )

            if it == 1:
                user_text = (
                    init_msg
                    + f"I've provided the tag name of each element and the text it contains "
                    f"(if text exists). Note that <textarea> or <input> may be textbox, "
                    f"but not exactly. Please focus more on the screenshot and then refer "
                    f"to the textual information.\n{web_eles_text}"
                )
            else:
                user_text = (
                    f"Observation:{warn_obs} please analyze the attached screenshot "
                    f"({visible_range}) and give the Thought and Action. "
                    f"I've provided the tag name of each element and the text it contains "
                    f"(if text exists). Note that <textarea> or <input> may be textbox, "
                    f"but not exactly. Please focus more on the screenshot and then refer "
                    f"to the textual information.\n{web_eles_text}"
                )

            curr_msg = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                ],
            }
            messages.append(curr_msg)
        else:
            messages.append({"role": "user", "content": fail_obs})

        # --- Clip context ---
        clip_msgs = clip_message_and_obs(messages, MAX_ATTACHED_IMGS)

        # --- LLM call ---
        api_start = time.time()
        try:
            pt, ct, res_text = call_llm(clip_msgs)
            total_prompt_tokens += pt
            total_completion_tokens += ct
            logging.info(f"Tokens  prompt={pt}  completion={ct}")
        except Exception as e:
            logging.error(f"LLM API error: {e}")
            break
        api_elapsed = time.time() - api_start

        messages.append({"role": "assistant", "content": res_text})
        logging.info(f"LLM response ({api_elapsed:.1f}s):\n{res_text}")

        # --- Remove annotations ---
        if rects:
            for r in rects:
                try:
                    driver.execute_script("arguments[0].remove()", r)
                except Exception:
                    pass
            rects = []

        # --- Parse action ---
        if "Thought:" not in res_text or "Action:" not in res_text:
            fail_obs = "Format ERROR: Both 'Thought' and 'Action' should be included in your reply."
            logging.warning(fail_obs)
            timings.append({"iter": it, "api_sec": api_elapsed, "total_sec": time.time() - iter_start})
            continue

        pattern = r"Thought:|Action:|Observation:"
        chosen_action = re.split(pattern, res_text)[2].strip()
        action_key, info = extract_information(chosen_action)
        logging.info(f"Action: {action_key}  Info: {info}")

        fail_obs = ""
        warn_obs = ""

        # --- Execute action ---
        try:
            if action_key == "click":
                ele_num = int(info[0])
                web_ele = web_eles[ele_num]
                driver.execute_script("arguments[0].setAttribute('target','_self')", web_ele)
                web_ele.click()
                time.sleep(3)

            elif action_key == "type":
                ele_num = int(info["number"])
                web_ele = web_eles[ele_num]
                ele_tag = web_ele.tag_name.lower()
                ele_type = web_ele.get_attribute("type")
                if (ele_tag not in ("input", "textarea")) or (
                    ele_tag == "input" and ele_type not in ("text", "search", "password", "email", "tel")
                ):
                    warn_obs = f"note: element <{ele_tag}> type={ele_type} may not be a textbox."

                try:
                    web_ele.clear()
                    if platform.system() == "Darwin":
                        web_ele.send_keys(Keys.COMMAND + "a")
                    else:
                        web_ele.send_keys(Keys.CONTROL + "a")
                    web_ele.send_keys(" ")
                    web_ele.send_keys(Keys.BACKSPACE)
                except Exception:
                    pass

                actions = ActionChains(driver)
                actions.click(web_ele).perform()
                time.sleep(1)

                try:
                    driver.execute_script(
                        'window.onkeydown = function(e) {'
                        'if(e.keyCode == 32 && e.target.type != "text" '
                        '&& e.target.type != "textarea" && e.target.type != "search")'
                        '{e.preventDefault();}};'
                    )
                except Exception:
                    pass

                type_content = info["content"].strip('"')
                actions = ActionChains(driver)
                actions.send_keys(type_content)
                actions.pause(2)
                actions.send_keys(Keys.ENTER)
                actions.perform()
                time.sleep(10)

            elif action_key == "scroll":
                scroll_target = info["number"]
                direction = info["content"]
                if scroll_target == "WINDOW":
                    delta = WINDOW_HEIGHT * 2 // 3
                    driver.execute_script(
                        f"window.scrollBy(0, {delta if direction == 'down' else -delta});"
                    )
                else:
                    ele_num = int(scroll_target)
                    web_ele = web_eles[ele_num]
                    act = ActionChains(driver)
                    driver.execute_script("arguments[0].focus();", web_ele)
                    if direction == "down":
                        act.key_down(Keys.ALT).send_keys(Keys.ARROW_DOWN).key_up(Keys.ALT).perform()
                    else:
                        act.key_down(Keys.ALT).send_keys(Keys.ARROW_UP).key_up(Keys.ALT).perform()
                time.sleep(2)

            elif action_key == "wait":
                time.sleep(5)

            elif action_key == "goback":
                driver.back()
                time.sleep(2)

            elif action_key == "google":
                driver.get("https://www.google.com/")
                time.sleep(2)

            elif action_key == "answer":
                logging.info(f"ANSWER: {info['content']}")
                iter_elapsed = time.time() - iter_start
                timings.append({"iter": it, "api_sec": api_elapsed, "total_sec": iter_elapsed})
                action_log.append({"iter": it, "action": action_key, "info": info, "response": res_text})
                # Save final screenshot
                driver.save_screenshot(os.path.join(screenshot_dir, "screenshot_final.png"))
                break

            else:
                logging.warning(f"Unknown action: {action_key}")

            # Handle new tabs/windows
            try:
                handles = driver.window_handles
                if len(handles) > 1:
                    driver.switch_to.window(handles[-1])
                elif handles:
                    driver.switch_to.window(handles[0])
            except Exception:
                pass

        except Exception as e:
            logging.error(f"Action execution error: {e}")
            if "element click intercepted" not in str(e):
                fail_obs = (
                    "The action you have chosen cannot be executed. Please double-check "
                    "if you have selected the wrong Numerical Label or Action or Action format. "
                    "Then provide the revised Thought and Action."
                )
            time.sleep(2)

        iter_elapsed = time.time() - iter_start
        timings.append({"iter": it, "api_sec": api_elapsed, "total_sec": iter_elapsed})
        action_log.append({
            "iter": it,
            "action": action_key,
            "info": info if isinstance(info, dict) else (list(info) if info else None),
            "response": res_text,
        })

    # --- Save final screenshot if not already saved ---
    final_path = os.path.join(screenshot_dir, "screenshot_final.png")
    try:
        if not os.path.exists(final_path):
            driver.save_screenshot(final_path)
    except Exception:
        logging.warning("Could not save final screenshot (browser may have closed)")

    try:
        driver.quit()
    except Exception:
        pass

    # --- Save logs ---
    with open(os.path.join(screenshot_dir, "action_log.json"), "w", encoding="utf-8") as f:
        json.dump(action_log, f, indent=2, ensure_ascii=False)

    with open(os.path.join(screenshot_dir, "timings.json"), "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2)

    # --- Cost summary ---
    # Claude Sonnet 4: $3/M input, $15/M output
    input_cost = total_prompt_tokens / 1_000_000 * 3
    output_cost = total_completion_tokens / 1_000_000 * 15
    total_cost = input_cost + output_cost

    summary = {
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "estimated_cost_usd": round(total_cost, 4),
        "iterations": len(timings),
        "timings": timings,
    }
    with open(os.path.join(screenshot_dir, "cost_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    logging.info(f"Prompt tokens: {total_prompt_tokens}")
    logging.info(f"Completion tokens: {total_completion_tokens}")
    logging.info(f"Estimated cost: ${total_cost:.4f}")
    logging.info("Done.")


if __name__ == "__main__":
    main()
