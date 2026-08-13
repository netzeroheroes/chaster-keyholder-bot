"""Games / tasks and extension-based punishments tied to Chaster plugins."""

from __future__ import annotations

from dataclasses import dataclass

from app.chaster_actions import ChasterIntent


@dataclass(frozen=True)
class ExtensionGame:
    id: str
    title: str
    needs: str  # extension slug or duo action
    how: str
    task: str  # assignable Tasks text when relevant


# Catalog for Domme + AI — real levers only (what this bot can drive)
EXTENSION_GAMES: list[ExtensionGame] = [
    ExtensionGame(
        id="share_link_hunt",
        title="Share-link hunt",
        needs="link",
        how=(
            "Harden share links (big add / tiny remove), then order the lockee to post "
            "his Chaster share link and collect visits. Each visit stacks time."
        ),
        task="Post your Chaster share link where told and collect the visits ordered. No begging to unlock.",
    ),
    ExtensionGame(
        id="share_link_roulette",
        title="Share-link roulette",
        needs="link",
        how=(
            "Set share links with random enabled if available, or harsh +/small -. "
            "Lockee must beg for mercy on punishments between visits — not for unlock."
        ),
        task="Survive share-link roulette: thank each visitor and report the count when asked.",
    ),
    ExtensionGame(
        id="pillory_hour",
        title="Pillory hour",
        needs="pillory",
        how="Start pillory for a set duration; lockee may only beg to ease stacking punishments.",
        task="Hold position for pillory. No topping from the bottom. Beg only to ease punishments.",
    ),
    ExtensionGame(
        id="verification_snap",
        title="Verification snap",
        needs="verification-picture",
        how="Request a verification picture; failure / delay earns more lock time.",
        task="Send the verification picture promptly when requested. Delay = more time.",
    ),
    ExtensionGame(
        id="task_ladder",
        title="Task ladder",
        needs="tasks",
        how="Assign escalating Tasks-extension jobs. Fail / skip = add time + hide timer.",
        task="Complete the assigned Chaster task fully, then wait for the next order.",
    ),
    ExtensionGame(
        id="hygiene_tease",
        title="Hygiene tease window",
        needs="temporary-opening",
        how=(
            "Shorten hygiene opening / raise overtime penalty. Cleaning is a privilege — "
            "not release. He begs to keep the window, not to stay unlocked."
        ),
        task="Use hygiene only as ordered. Overtime earns the penalty. No freestyle unlock begging.",
    ),
    ExtensionGame(
        id="freeze_corner",
        title="Frozen corner",
        needs="duo-domme",
        how="Freeze the lock, hide timer, assign stillness / lines. Unfreeze only if Dommes allow.",
        task="Stay frozen in posture/lines until keyholders unfreeze you. Beg only to ease punishments.",
    ),
]


def games_prompt_block() -> str:
    lines = [
        "EXTENSION GAMES / TASKS (use real plugins on the lock - activate first if missing):",
    ]
    for g in EXTENSION_GAMES:
        lines.append(f"- {g.title} [{g.needs}]: {g.how}")
    lines.append(
        "When punishing with extensions: configure share links harshly, pillory, "
        "assign Tasks, request verification — then narrate briefly. Never invent plugin results."
    )
    return "\n".join(lines)


def share_link_punish_config(
    strike: int,
    *,
    current_add: int = 0,
    current_remove: int = 0,
) -> str:
    """Harsher share-link +/- as strikes climb (reason body for configure_share_links)."""
    n = max(1, int(strike or 1))
    # Always move past current config so Chaster shows a real change
    add = min(12 * 3600, max(2 * 3600 * n, int(current_add or 0) + 3600 * n))
    # Shrink remove; if already tiny, leave at 0
    target_remove = max(0, 900 // n)  # 15m, 7m, 5m…
    if int(current_remove or 0) > 0:
        remove = min(int(current_remove), target_remove)
        if remove == int(current_remove) and remove > 0:
            remove = max(0, remove // 2)
    else:
        remove = target_remove
    return f"add:{add}|remove:{remove}"


def punish_task_for_strike(strike: int, reason: str) -> str:
    n = max(1, int(strike or 1))
    base = (reason or "disobedience").strip()[:80]
    if n >= 4:
        return (
            f"Strike {n}: write 20 lines — I obey my keyholders — then edge twice "
            f"without release. Cause: {base}"
        )
    if n >= 3:
        return (
            f"Strike {n}: kneel, hands behind back, count 120 slow breaths. "
            f"Cause: {base}"
        )
    if n >= 2:
        return (
            f"Strike {n}: edge once with no release, then cage check photo if asked. "
            f"Cause: {base}"
        )
    return (
        f"Strike {n}: apologize properly to your keyholders and wait for the next order. "
        f"Cause: {base}"
    )


def extension_punish_intents(
    strike: int,
    *,
    reason: str,
    share_add: int = 0,
    share_remove: int = 0,
) -> list[ChasterIntent]:
    """
    Extra extension levers for escalating disobedience.
    Intents that fail (plugin missing) are skipped by the action runner as blocked.
    """
    n = max(1, int(strike or 1))
    out: list[ChasterIntent] = []
    # Always try to harden share links from strike 1 when escalating attitude
    out.append(
        ChasterIntent(
            kind="configure_share_links",
            reason=share_link_punish_config(
                n, current_add=share_add, current_remove=share_remove
            ),
        )
    )
    if n >= 2:
        out.append(
            ChasterIntent(
                kind="assign_task",
                reason=punish_task_for_strike(n, reason),
            )
        )
    if n >= 3:
        # Pillory duration grows with strike (5m, 10m, 15m…)
        out.append(
            ChasterIntent(
                kind="pillory",
                seconds=min(3600, 300 * (n - 1)),
                reason=f"strike {n}: {reason}"[:120],
            )
        )
    if n >= 4:
        out.append(ChasterIntent(kind="request_verification", reason=f"strike {n}"))
    return out
