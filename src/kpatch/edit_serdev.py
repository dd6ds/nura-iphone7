#!/usr/bin/env python3
# Fügt serdev_device_set_stopbits() hinzu (für HDQ-über-UART, braucht 2 Stoppbits)
import pathlib, sys
T = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12"

def sub(path, old, new):
    p = T / path; s = p.read_text()
    if new in s: return
    if s.count(old) != 1: sys.exit(f"{path}: Anker nicht eindeutig: {old[:40]!r}")
    p.write_text(s.replace(old, new))

sub("include/linux/serdev.h",
    "\tint (*set_parity)(struct serdev_controller *, enum serdev_parity);\n",
    "\tint (*set_parity)(struct serdev_controller *, enum serdev_parity);\n"
    "\tint (*set_stopbits)(struct serdev_controller *, unsigned int);\n")
sub("include/linux/serdev.h",
    "int serdev_device_set_parity(struct serdev_device *serdev,\n",
    "int serdev_device_set_stopbits(struct serdev_device *serdev,\n"
    "\t\t\t       unsigned int stopbits);\n"
    "int serdev_device_set_parity(struct serdev_device *serdev,\n")
sub("drivers/tty/serdev/core.c",
    "EXPORT_SYMBOL_GPL(serdev_device_set_parity);\n",
    "EXPORT_SYMBOL_GPL(serdev_device_set_parity);\n\n"
    "int serdev_device_set_stopbits(struct serdev_device *serdev,\n"
    "\t\t\t       unsigned int stopbits)\n{\n"
    "\tstruct serdev_controller *ctrl = serdev->ctrl;\n\n"
    "\tif (!ctrl || !ctrl->ops->set_stopbits)\n\t\treturn -EOPNOTSUPP;\n\n"
    "\treturn ctrl->ops->set_stopbits(ctrl, stopbits);\n}\n"
    "EXPORT_SYMBOL_GPL(serdev_device_set_stopbits);\n")
sub("drivers/tty/serdev/serdev-ttyport.c",
    "static int ttyport_set_parity(struct serdev_controller *ctrl,\n",
    "static int ttyport_set_stopbits(struct serdev_controller *ctrl,\n"
    "\t\t\t\tunsigned int stopbits)\n{\n"
    "\tstruct serport *serport = serdev_controller_get_drvdata(ctrl);\n"
    "\tstruct tty_struct *tty = serport->tty;\n"
    "\tstruct ktermios ktermios = tty->termios;\n\n"
    "\tif (stopbits != 1 && stopbits != 2)\n\t\treturn -EINVAL;\n\n"
    "\tif (stopbits == 2)\n\t\tktermios.c_cflag |= CSTOPB;\n"
    "\telse\n\t\tktermios.c_cflag &= ~CSTOPB;\n\n"
    "\ttty_set_termios(tty, &ktermios);\n\n"
    "\treturn (tty->termios.c_cflag & CSTOPB) == (ktermios.c_cflag & CSTOPB) ?\n"
    "\t\t0 : -EINVAL;\n}\n\n"
    "static int ttyport_set_parity(struct serdev_controller *ctrl,\n")
sub("drivers/tty/serdev/serdev-ttyport.c",
    "\t.set_parity = ttyport_set_parity,\n",
    "\t.set_parity = ttyport_set_parity,\n\t.set_stopbits = ttyport_set_stopbits,\n")
print("serdev ok")
