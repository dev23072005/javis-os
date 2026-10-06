"""Hồi quy: cổng env tạm dừng thực thi reminder khi chuyển Javis sang máy khác.

Chạy:
    python tests/python/test_reminder_execution_gate.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401

import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reminder-gate-state-")

import reminders  # noqa: E402


fails = []
checks = 0


def check(name, cond):
    global checks
    checks += 1
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def feature_with_scheduler(scheduler):
    async def send(_chat_id, _text):
        return True, ""

    return reminders.RemindersFeature(reminders.RemindersDeps(
        brain_root=lambda brain: tempfile.gettempdir(),
        atomic_write_text=lambda _path, _text: None,
        send_telegram=send,
        build_system_prompt=lambda _brain: "",
        aux_model=lambda: None,
        safe_tools=[],
        readonly_tools=[],
        scheduler_brains=scheduler,
    ))


async def run():
    env = reminders.REMINDER_EXECUTION_ENV
    old = os.environ.get(env)
    try:
        os.environ.pop(env, None)
        check("không đặt env thì mặc định vẫn thực thi",
              reminders.reminder_execution_enabled())

        truthy = ("1", "true", "YES", " on ")
        check("các giá trị bật được chấp nhận",
              all((os.environ.__setitem__(env, value) is None
                   and reminders.reminder_execution_enabled()) for value in truthy))

        falsy = ("0", "false", "NO", " off ")
        check("các giá trị tắt được chấp nhận",
              all((os.environ.__setitem__(env, value) is None
                   and not reminders.reminder_execution_enabled()) for value in falsy))

        scheduler_calls = []
        feature = feature_with_scheduler(lambda: scheduler_calls.append("called") or ["brain"])
        os.environ[env] = "false"
        await feature.tick()
        check("khi tắt, tick không đọc brain và không thực thi", scheduler_calls == [])

        ticked = []

        async def fake_tick_brain(brain):
            ticked.append(brain)

        feature._tick_brain = fake_tick_brain
        os.environ[env] = "true"
        await feature.tick()
        check("bật lại thì tick tiếp tục ngay đường cũ",
              scheduler_calls == ["called"] and ticked == ["brain"])

        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        hostinger = (ROOT / "docker-compose.hostinger.yml").read_text(encoding="utf-8")
        needle = "JAVIS_REMINDER_EXECUTION_ENABLED: ${JAVIS_REMINDER_EXECUTION_ENABLED:-true}"
        check("hai compose truyền cổng env với mặc định tương thích",
              needle in compose and needle in hostinger)
    finally:
        if old is None:
            os.environ.pop(env, None)
        else:
            os.environ[env] = old


asyncio.run(run())

if fails:
    print(f"\nFAIL - test_reminder_execution_gate: {len(fails)}/{checks} lỗi: {fails}")
    raise SystemExit(1)
print(f"\nOK - test_reminder_execution_gate: {checks}/{checks} pass")
