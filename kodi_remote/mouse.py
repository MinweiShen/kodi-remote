"""Relative uinput mouse, with time-based acceleration and fractional carry."""
import math


class Mouse:
    def __init__(self, demo=False):
        self.device = None
        self.pressed = set()
        self.remainder = [0.0, 0.0]
        self.speed = 0.0
        if not demo:
            from evdev import UInput, ecodes as e
            self.e = e
            self.device = UInput({e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT],
                                 e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL]},
                                name="Kodi Browser Remote")

    def move(self, dx, dy, dt, sensitivity=3, acceleration=True):
        speed = math.hypot(dx, dy) / max(dt, 1)
        alpha = 1 - math.exp(-max(dt, 1) / 35)
        self.speed += alpha * (speed - self.speed)
        t = max(0, min(1, (self.speed - .15) / 1.05))
        gain = sensitivity * (1 + (2 * t * t * (3 - 2 * t) if acceleration else 0))
        result = []
        for i, value in enumerate((dx, dy)):
            total = value * gain + self.remainder[i]
            whole = math.trunc(total)
            self.remainder[i] = total - whole
            result.append(whole)
        if self.device:
            self.device.write(self.e.EV_REL, self.e.REL_X, result[0])
            self.device.write(self.e.EV_REL, self.e.REL_Y, result[1])
            self.device.syn()
        return result

    def button(self, button, down):
        if down:
            self.pressed.add(button)
        else:
            self.pressed.discard(button)
        if self.device:
            code = self.e.BTN_LEFT if button == "left" else self.e.BTN_RIGHT
            self.device.write(self.e.EV_KEY, code, int(down))
            self.device.syn()

    def scroll(self, steps):
        if self.device:
            self.device.write(self.e.EV_REL, self.e.REL_WHEEL, steps)
            self.device.syn()

    def release(self):
        for button in list(self.pressed):
            self.button(button, False)
        self.speed = 0
        self.remainder = [0.0, 0.0]

    def close(self):
        self.release()
        if self.device:
            self.device.close()
