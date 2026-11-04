"""Verify task creation preserves matrix account selection after frontend build."""
import asyncio
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from playwright.async_api import async_playwright


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file():
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, *_args):
        pass


async def check(browser, base, width):
    page = await browser.new_page(viewport={"width": width, "height": 1000})
    errors, submitted = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    accounts = [
        {"id": "douyin-1", "platform": "douyin", "label": "抖音账号1", "status": "authorized"},
        {"id": "douyin-2", "platform": "douyin", "label": "抖音账号2", "status": "authorized"},
        {"id": "channels-1", "platform": "wechat_channels", "label": "视频号账号1", "status": "session_saved"},
    ]

    async def api(route):
        path = urlparse(route.request.url).path.split("/api/v1")[-1]
        result = {}
        if path == "/auth/refresh":
            result = {"access_token": "mock"}
        elif path == "/auth/me":
            result = {"id": "user", "email": "test@example.invalid", "is_active": True}
        elif path == "/companies":
            result = [{"id": "company", "name": "测试酒店"}]
        elif path.endswith("/employees"):
            result = [{"id": "employee", "name": "视频制作员", "role_title": "video_producer",
                       "role": "video_producer", "is_active": True, "description": "视频制作"}]
        elif path.endswith("/publishing/accounts"):
            result = accounts
        elif path.endswith("/tasks") and route.request.method == "POST":
            submitted.append(route.request.post_data_json)
            await route.fulfill(status=422, content_type="application/json",
                                body=json.dumps({"detail": "UI validation only"}))
            return
        await route.fulfill(status=200, content_type="application/json", body=json.dumps(result))

    await page.route("**/api/v1/**", api)
    await page.add_init_script(
        "localStorage.setItem('refresh_token','mock');localStorage.setItem('currentCompanyId','company')"
    )
    await page.goto(base + "/tasks/new?role=video_producer")
    await page.get_by_text("目标发布账号", exact=True).wait_for()
    picker = page.locator(".n-form-item").filter(has_text="目标发布账号").locator(".n-base-selection")
    await picker.click()
    for label in ("抖音 · 抖音账号1", "抖音 · 抖音账号2", "视频号 · 视频号账号1"):
        await page.get_by_text(label, exact=True).click()
    await page.keyboard.press("Escape")
    await page.get_by_placeholder("例如：本周酒店运营分析").fill("矩阵账号回归测试")
    await page.get_by_placeholder("说明你要解决的问题、目标客群和交付要求").fill("为所选账号生成酒店视频")
    await page.get_by_role("button", name="提交并执行", exact=True).click()
    await page.get_by_text("UI validation only", exact=True).wait_for()

    params = submitted[0]["input_params"]
    assert params["publish_account_ids"] == ["douyin-1", "douyin-2", "channels-1"]
    assert "publish_platforms" not in params
    assert params["reuse_policy"] == "prefer_reuse"
    assert not errors, errors
    print(f"PASS {width}px: selected matrix account IDs and reuse policy are submitted", flush=True)
    await page.close()


async def main():
    dist = Path(__file__).resolve().parents[1] / "dist"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(dist)))
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                args=["--no-sandbox"],
            )
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                for width in (1440, 390):
                    await check(browser, base, width)
            finally:
                await browser.close()
    finally:
        server.shutdown()


asyncio.run(main())
