"""Games / tasks and extension-based punishments tied to real Chaster plugins."""

from __future__ import annotations

from dataclasses import dataclass

from app.chaster_actions import (
    DEFAULT_PILLORY_TIME_TO_ADD,
    DEFAULT_SHARE_MIN_VISITS,
    ChasterIntent,
    _encode_config_parts,
)


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
            "Harden share links: fat timeToAdd, tiny/zero timeToRemove, "
            f"nbVisits≈{DEFAULT_SHARE_MIN_VISITS} (min visits before unlock), "
            "anyone can click. Order him to post his Chaster share URL and collect visits."
        ),
        task=(
            "Post your Chaster share link where told and collect the required visits. "
            "No begging to unlock."
        ),
    ),
    ExtensionGame(
        id="share_link_roulette",
        title="Share-link roulette",
        needs="link",
        how=(
            "enableRandom=true with harsh + / tiny − so each visit is a coin-flip sting. "
            "Raise nbVisits so he stays trapped until the community has toyed with him."
        ),
        task="Survive share-link roulette: thank each visitor and report the count when asked.",
    ),
    ExtensionGame(
        id="pillory_hour",
        title="Pillory window",
        needs="pillory",
        how=(
            "Set pillory timeToAdd (seconds each public vote adds — start ~10m), "
            "limitToLoggedUsers=false, then start a voting WINDOW via Duo Domme "
            "(duration + humiliating reason on the Activity feed)."
        ),
        task="Hold for pillory. Beg only to ease stacking punishments — not to unlock.",
    ),
    ExtensionGame(
        id="verification_snap",
        title="Verification snap",
        needs="verification-picture",
        how="Request a verification picture; delay earns more lock time / freeze.",
        task="Send the verification picture promptly when requested. Delay = more time.",
    ),
    ExtensionGame(
        id="task_ladder",
        title="Task ladder",
        needs="tasks",
        how=(
            "Lock down Tasks config (no wearer self-assign), abandoned-task add-time, "
            "then assign escalating jobs via the Tasks API."
        ),
        task="Complete the assigned Chaster task fully, then wait for the next order.",
    ),
    ExtensionGame(
        id="hygiene_tease",
        title="Hygiene tease window",
        needs="temporary-opening",
        how=(
            "Short openingTime, fat penaltyTime, freezeLockWhileOpen, "
            "requireVerificationPictureAfter. Cleaning is a privilege, not release."
        ),
        task="Use hygiene only as ordered. Overtime earns the penalty.",
    ),
    ExtensionGame(
        id="dice_stakes",
        title="Dice stakes",
        needs="dice",
        how=(
            "Raise dice multiplier (time per pip difference), then force rolls in Chaster. "
            "Bot cannot remote-roll — he plays; we react from history."
        ),
        task="Roll when ordered. Report the result. Losing pips stack time.",
    ),
    ExtensionGame(
        id="cruel_wheel",
        title="Cruel wheel",
        needs="wheel-of-fortune",
        how=(
            "Rewrite wheel segments toward add-time / freeze / pillory / dare text "
            "with only a crumb of remove-time. He spins in Chaster; we gloat."
        ),
        task="Spin when ordered. Accept the segment. No topping from the bottom.",
    ),
    ExtensionGame(
        id="random_terror",
        title="Random terror",
        needs="random-events",
        how="Set random-events difficulty to hard/expert so surprises keep landing.",
        task="Stay available. Random events are not negotiable.",
    ),
    ExtensionGame(
        id="puzzle_trap",
        title="Puzzle trap",
        needs="jigsaw-puzzle",
        how=(
            "More pieces, timed puzzles, freezeWhenAvailable, ADD_TIME punishments. "
            "He solves in Chaster; failure stacks time."
        ),
        task="Clear assigned puzzles before the timer. Failures add time.",
    ),
    ExtensionGame(
        id="freeze_corner",
        title="Frozen corner",
        needs="duo-domme",
        how="Freeze the lock, hide timer, assign stillness / lines. Unfreeze only if Dommes allow.",
        task="Stay frozen in posture/lines until keyholders unfreeze you.",
    ),
]


def games_prompt_block() -> str:
    lines = [
        "EXTENSION GAMES / TORMENT (real Chaster config fields — activate first if missing):",
    ]
    for g in EXTENSION_GAMES:
        lines.append(f"- {g.title} [{g.needs}]: {g.how}")
    lines.append(
        "Punish with REAL levers: share-link +/- + nbVisits; pillory window + timeToAdd; "
        "hygiene open/penalty; Tasks assign; verification request; dice multiplier; "
        "wheel segments; random-events difficulty; jigsaw punishments. "
        "Never invent vote quotas Chaster does not have. Never invent plugin results."
    )
    return "\n".join(lines)


def share_link_punish_config(
    strike: int,
    *,
    current_add: int = 0,
    current_remove: int = 0,
    current_visits: int = 0,
) -> str:
    """Harsher share-link +/- and min visits as strikes climb."""
    n = max(1, int(strike or 1))
    add = min(12 * 3600, max(2 * 3600 * n, int(current_add or 0) + 3600 * n))
    target_remove = max(0, 900 // n)
    if int(current_remove or 0) > 0:
        remove = min(int(current_remove), target_remove)
        if remove == int(current_remove) and remove > 0:
            remove = max(0, remove // 2)
    else:
        remove = target_remove
    # Minimum visits before unlock — start small (~10), climb with strikes
    visits = max(
        DEFAULT_SHARE_MIN_VISITS,
        int(current_visits or 0),
        DEFAULT_SHARE_MIN_VISITS + (n - 1) * 2,
    )
    visits = min(40, visits)
    return _encode_config_parts(
        {
            "add": add,
            "remove": remove,
            "visits": visits,
            "random": True,
            "logged": False,
            "visible": True,
        }
    )


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
    share_visits: int = 0,
) -> list[ChasterIntent]:
    """
    Extra extension levers for escalating disobedience.
    Uses catalog-backed fields only; missing plugins come back blocked.
    """
    n = max(1, int(strike or 1))
    out: list[ChasterIntent] = []
    # Strike 1+: trap him behind share-link visits + harsh +/-
    out.append(
        ChasterIntent(
            kind="configure_share_links",
            reason=share_link_punish_config(
                n,
                current_add=share_add,
                current_remove=share_remove,
                current_visits=share_visits,
            ),
            votes=max(DEFAULT_SHARE_MIN_VISITS, DEFAULT_SHARE_MIN_VISITS + (n - 1) * 2),
        )
    )
    if n >= 2:
        out.append(
            ChasterIntent(
                kind="configure_extension",
                title="tasks",
                reason="torment:1",
            )
        )
        out.append(
            ChasterIntent(
                kind="assign_task",
                reason=punish_task_for_strike(n, reason),
            )
        )
    if n >= 3:
        # Pillory: longer window + climbing per-vote add (starts ~10 minutes)
        per_vote = min(3600, DEFAULT_PILLORY_TIME_TO_ADD * (n - 2))
        out.append(
            ChasterIntent(
                kind="pillory",
                seconds=min(3600, 300 * (n - 1)),
                time_to_add=per_vote,
                reason=f"strike {n}: {reason}"[:120],
            )
        )
        out.append(
            ChasterIntent(
                kind="configure_extension",
                title="dice",
                reason=_encode_config_parts({"multiplier": min(14400, 3600 * n)}),
            )
        )
    if n >= 4:
        out.append(ChasterIntent(kind="request_verification", reason=f"strike {n}"))
        out.append(
            ChasterIntent(
                kind="configure_extension",
                title="temporary-opening",
                reason="torment:1",
            )
        )
        out.append(
            ChasterIntent(
                kind="configure_extension",
                title="random-events",
                reason=_encode_config_parts({"difficulty": "hard"}),
            )
        )
    if n >= 5:
        out.append(
            ChasterIntent(
                kind="configure_extension",
                title="wheel-of-fortune",
                reason="torment:1",
            )
        )
        out.append(
            ChasterIntent(
                kind="configure_extension",
                title="jigsaw-puzzle",
                reason="torment:1",
            )
        )
    return out
