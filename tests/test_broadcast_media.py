import asyncio
from types import SimpleNamespace

import pytest

from BOOKzMA.services import broadcast


class Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


class SessionPool:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return SessionContext(self.session)


@pytest.mark.parametrize("media_type", [None, "photo", "video"])
def test_send_one_delivers_campaign_content_and_https_button(monkeypatch, media_type):
    async def run_test():
        campaign = SimpleNamespace(
            id=5,
            audience="miswak",
            text="یادگیری",
            media_type=media_type,
            media_file_id="telegram-file-id" if media_type else None,
            button_label="مشاهده",
            button_url="https://example.com/guide",
        )
        delivery = SimpleNamespace(id=9, user_id=77, attempts=0)
        session = Session()
        calls = []
        states = []

        async def next_delivery(_session):
            return campaign, delivery

        async def eligible_recipient(_session, _campaign, _user_id):
            return True

        async def set_delivery_state(_session, _delivery_id, state, *_args):
            states.append(state)

        async def send_media(*args, **kwargs):
            calls.append((args, kwargs))

        monkeypatch.setattr(broadcast.broadcasts, "next_delivery", next_delivery)
        monkeypatch.setattr(broadcast.broadcasts, "eligible_recipient", eligible_recipient)
        monkeypatch.setattr(broadcast.broadcasts, "set_delivery_state", set_delivery_state)
        bot = SimpleNamespace(
            send_message=send_media,
            send_photo=send_media,
            send_video=send_media,
        )

        assert await broadcast.send_one(bot, SessionPool(session))
        assert len(calls) == 1
        expected_content = "telegram-file-id" if media_type else "یادگیری"
        assert calls[0][0][:2] == (77, expected_content)
        if media_type:
            assert calls[0][1]["caption"] == "یادگیری"
        assert calls[0][1]["parse_mode"] is None
        button = calls[0][1]["reply_markup"].inline_keyboard[0][0]
        assert button.url == "https://example.com/guide"
        assert states == ["sending", "sent"]
        assert session.commits == 2

    asyncio.run(run_test())


def test_send_one_skips_cohort_member_who_left_before_delivery(monkeypatch):
    async def run_test():
        campaign = SimpleNamespace(id=5, audience="miswak")
        delivery = SimpleNamespace(id=9, user_id=77, attempts=0)
        session = Session()
        states = []
        sent = []

        async def next_delivery(_session):
            return campaign, delivery

        async def eligible_recipient(_session, _campaign, _user_id):
            return False

        async def set_delivery_state(_session, _delivery_id, state, *_args):
            states.append(state)

        async def send_message(*args, **kwargs):
            sent.append((args, kwargs))

        monkeypatch.setattr(broadcast.broadcasts, "next_delivery", next_delivery)
        monkeypatch.setattr(broadcast.broadcasts, "eligible_recipient", eligible_recipient)
        monkeypatch.setattr(broadcast.broadcasts, "set_delivery_state", set_delivery_state)

        assert await broadcast.send_one(
            SimpleNamespace(send_message=send_message), SessionPool(session)
        )
        assert sent == []
        assert delivery.attempts == 0
        assert states == ["cancelled"]
        assert session.commits == 1

    asyncio.run(run_test())