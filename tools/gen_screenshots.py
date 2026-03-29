"""Generate curated screenshots from a real game for README docs/images/."""

import asyncio
from pathlib import Path

from textual.app import App
from sts2_tui.bridge import EngineBridge
from sts2_tui.tui.screens.combat import CombatScreen
from sts2_tui.tui.screens.card_reward import CardRewardScreen
from sts2_tui.tui.screens.event import EventScreen
from sts2_tui.tui.screens.rest import RestScreen
from sts2_tui.tui.screens.shop import ShopScreen
from sts2_tui.tui.screens.map import MapScreen
from sts2_tui.tui.controller import GameController

OUT = Path("docs/images")
OUT.mkdir(parents=True, exist_ok=True)
CSS = str(Path("sts2_tui/tui/sls.tcss").resolve())
SIZE = (180, 50)
MAP_SIZE = (180, 90)  # taller for full map visibility


async def screenshot(screen_cls, state, ctrl, name):
    ctrl.current_state = state
    use_size = MAP_SIZE if "map" in name else SIZE

    class ScreenApp(App):
        CSS_PATH = CSS
        async def on_mount(self):
            self.push_screen(screen_cls(state, controller=ctrl))

    app = ScreenApp()
    async with app.run_test(size=use_size) as pilot:
        await pilot.pause(delay=0.5)
        app.save_screenshot(str(OUT / name))
        print(f"  OK: {name}")


async def main():
    bridge = EngineBridge()
    await bridge.start()
    ctrl = GameController(bridge)

    # Use god mode to reach more screen types
    state = await ctrl.start_run("Ironclad", seed="42", god_mode=True)

    captured = {}
    screen_map = {
        "combat": CombatScreen,
        "card_reward": CardRewardScreen,
        "event": EventScreen,
        "rest": RestScreen,
        "shop": ShopScreen,
        "map": MapScreen,
    }

    print("Playing game to capture screenshots...")

    for step in range(300):
        decision = state.get("decision", "")

        floor = state.get("context", {}).get("floor", 0)
        if decision == "combat_play" and "combat" not in captured and floor >= 2:
            # Skip floor 1 combats — too simple. Get a mid-game one.
            captured["combat"] = dict(state)
            print(f"  Captured: combat (floor {floor})")
        elif decision == "card_reward" and "card_reward" not in captured:
            captured["card_reward"] = dict(state)
            print(f"  Captured: card_reward (floor {floor})")
        elif decision == "event_choice" and "event" not in captured and floor >= 2:
            # Skip Neow — get a real event
            captured["event"] = dict(state)
            print(f"  Captured: event (floor {floor})")
        elif decision == "rest_site" and "rest" not in captured:
            captured["rest"] = dict(state)
            print(f"  Captured: rest (floor {floor})")
        elif decision == "shop" and "shop" not in captured:
            captured["shop"] = dict(state)
            print(f"  Captured: shop (floor {floor})")
        elif decision == "map_select" and "map" not in captured and floor >= 3:
            # Skip early map — get one with some progress
            captured["map"] = dict(state)
            print(f"  Captured: map (floor {floor})")

        # Navigate
        if decision == "combat_play":
            hand = state.get("hand", [])
            energy = state.get("energy", 0)
            played = False
            for i, c in enumerate(hand):
                if c.get("can_play") and c.get("cost", 99) <= energy:
                    target = 0 if c.get("type") == "Attack" else None
                    state = await ctrl.play_card(i, target)
                    played = True
                    break
            if not played:
                state = await ctrl.end_turn()
        elif decision == "map_select":
            choices = state.get("choices", [])
            if choices:
                c = choices[0]
                state = await ctrl.select_map_node(c.get("col", 0), c.get("row", 0))
            else:
                state = await ctrl.choose(0)
        elif decision == "card_reward":
            state = await ctrl.skip_card_reward()
        elif decision == "game_over":
            break
        else:
            state = await ctrl.choose(0)

        if state.get("type") == "error":
            try:
                state = await ctrl.proceed()
            except Exception:
                break

        if len(captured) >= 6:
            break

    print(f"\nCaptured {len(captured)}/{len(screen_map)} screen types")

    for name, s in captured.items():
        cls = screen_map.get(name)
        if cls:
            await screenshot(cls, s, ctrl, f"{name}.svg")

    await ctrl.quit()
    print(f"\nDone! Screenshots in {OUT}/")


if __name__ == "__main__":
    asyncio.run(main())
