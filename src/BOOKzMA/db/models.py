from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    CheckConstraint,
    String,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from BOOKzMA.constants import DEFAULT_TIMEZONE
from BOOKzMA.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    broadcast_unavailable: Mapped[bool] = mapped_column(default=False, server_default="false")
    timezone: Mapped[str] = mapped_column(
        String(64), default=DEFAULT_TIMEZONE, server_default=DEFAULT_TIMEZONE
    )
    leaderboard_opt_out: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # comeback streak (S-07): دورهٔ بازگشت فعال و پاداش جمع‌شده
    broken_streak_days: Mapped[int | None] = mapped_column(Integer)
    comeback_bonus_days: Mapped[int] = mapped_column(default=0, server_default="0")
    comeback_base_day: Mapped[date | None] = mapped_column(Date)


class ReadingLog(Base):
    __tablename__ = "reading_logs"
    __table_args__ = (Index("ix_reading_logs_day", "day"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StreakFreeze(Base):
    __tablename__ = "streak_freezes"
    __table_args__ = (
        CheckConstraint("kind IN ('earned', 'used')", name="ck_streak_freeze_kind"),
        UniqueConstraint("user_id", "kind", "day", name="uq_streak_freeze_user_kind_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8))
    day: Mapped[date] = mapped_column(Date)


class ActivityDay(Base):
    __tablename__ = "activity_days"
    __table_args__ = (Index("ix_activity_days_day", "day"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class StreakAlert(Base):
    """dedup روزانهٔ هشدار «استریک در خطر» (S-08)."""

    __tablename__ = "streak_alerts"
    __table_args__ = (Index("ix_streak_alerts_day", "day"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class Badge(Base):
    """نشان دستاورد (G-01)؛ اهدا ایدمپوتنت با unique (user_id, code)."""

    __tablename__ = "badges"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_badge_user_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32))
    awarded_day: Mapped[date] = mapped_column(Date)


class BuddyQueue(Base):
    """صف انتظار جفت‌شدن رفیق مطالعه (C-06)."""

    __tablename__ = "buddy_queue"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BuddyInvite(Base):
    """One-time, expiring deep-link invitation to a known study buddy."""

    __tablename__ = "buddy_invites"
    __table_args__ = (Index("ix_buddy_invites_inviter_id", "inviter_id"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    inviter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BuddyPair(Base):
    """Buddy relationship; a user may have many active pairs, but each pair is unique."""

    __tablename__ = "buddy_pairs"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'ended')", name="ck_buddy_pair_status"),
        CheckConstraint("user_a <> user_b", name="ck_buddy_pair_distinct"),
        Index(
            "uq_buddy_pair_active_pair",
            "user_a",
            "user_b",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_a: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    user_b: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[int | None] = mapped_column(BigInteger)
    last_nudge_on: Mapped[date | None] = mapped_column(Date)


class BroadcastCampaign(Base):
    __tablename__ = "broadcast_campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sending', 'completed', 'cancelled')",
            name="ck_broadcast_campaign_status",
        ),
        CheckConstraint(
            "audience IN ('all', 'miswak')", name="ck_broadcast_campaign_audience"
        ),
        CheckConstraint(
            "media_type IS NULL OR media_type IN ('photo', 'video')",
            name="ck_broadcast_campaign_media_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(String(4096))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    audience: Mapped[str] = mapped_column(String(16), default="all", server_default="all")
    media_type: Mapped[str | None] = mapped_column(String(8))
    media_file_id: Mapped[str | None] = mapped_column(String(512))
    button_label: Mapped[str | None] = mapped_column(String(64))
    button_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BroadcastDelivery(Base):
    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uq_broadcast_delivery_campaign_user"),
        Index("ix_broadcast_delivery_campaign_status", "campaign_id", "status"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')",
            name="ck_broadcast_delivery_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("broadcast_campaigns.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(128))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeletedAccount(Base):
    """سنگ‌قبر حساب حذف‌شده؛ بدون FK تا از حذف ردیف users جان سالم ببرد."""

    __tablename__ = "deleted_accounts"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reason: Mapped[str | None] = mapped_column(String(32))


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("user_id", "remind_at", name="uq_reminder_user_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    remind_at: Mapped[time] = mapped_column(Time)
    last_sent_on: Mapped[date | None] = mapped_column(Date)
    attempt_date: Mapped[date | None] = mapped_column(Date)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retry_after_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MiswakProfile(Base):
    __tablename__ = "miswak_profiles"
    __table_args__ = (
        CheckConstraint("daily_goal BETWEEN 1 AND 5", name="ck_miswak_profile_daily_goal"),
        CheckConstraint(
            "next_daily_goal IS NULL OR next_daily_goal BETWEEN 1 AND 5",
            name="ck_miswak_profile_next_goal",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    league_opt_in: Mapped[bool] = mapped_column(default=False, server_default="false")
    daily_goal: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    next_daily_goal: Mapped[int | None] = mapped_column(Integer)
    goal_effective_on: Mapped[date | None] = mapped_column(Date)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MiswakEntry(Base):
    __tablename__ = "miswak_entries"
    __table_args__ = (
        CheckConstraint("slot BETWEEN 1 AND 5", name="ck_miswak_entry_slot"),
        CheckConstraint("daily_goal BETWEEN 1 AND 5", name="ck_miswak_entry_goal"),
        CheckConstraint("slot <= daily_goal", name="ck_miswak_entry_slot_goal"),
        Index("ix_miswak_entries_day", "day"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_goal: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MiswakReminder(Base):
    __tablename__ = "miswak_reminders"
    __table_args__ = (
        CheckConstraint("slot BETWEEN 1 AND 5", name="ck_miswak_reminder_slot"),
        UniqueConstraint("user_id", "remind_at", name="uq_miswak_reminder_user_time"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("miswak_profiles.user_id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)
    remind_at: Mapped[time] = mapped_column(Time)
    last_sent_on: Mapped[date | None] = mapped_column(Date)
    attempt_date: Mapped[date | None] = mapped_column(Date)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retry_after_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MiswakBadge(Base):
    __tablename__ = "miswak_badges"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_miswak_badge_user_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32))
    awarded_day: Mapped[date] = mapped_column(Date)


class MiswakChallenge(Base):
    __tablename__ = "miswak_challenges"
    __table_args__ = (
        CheckConstraint("duration IN (7, 30)", name="ck_miswak_challenge_duration"),
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_miswak_challenge_status",
        ),
        Index(
            "uq_miswak_challenge_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    duration: Mapped[int] = mapped_column(Integer)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MiswakBuddyInvite(Base):
    __tablename__ = "miswak_buddy_invites"
    __table_args__ = (Index("ix_miswak_buddy_invites_inviter", "inviter_id"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    inviter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MiswakBuddyPair(Base):
    __tablename__ = "miswak_buddy_pairs"
    __table_args__ = (
        CheckConstraint("user_a < user_b", name="ck_miswak_buddy_pair_order"),
        CheckConstraint(
            "status IN ('active', 'ended')", name="ck_miswak_buddy_pair_status"
        ),
        Index(
            "uq_miswak_buddy_pair_active",
            "user_a",
            "user_b",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_a: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    user_b: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_nudge_on: Mapped[date | None] = mapped_column(Date)
