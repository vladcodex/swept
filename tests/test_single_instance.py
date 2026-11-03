"""Тесты ожидания единственного экземпляра.

Проверяют именно то, из-за чего приложение могло закрыться, не показав окна:
ShellExecuteW вернул «успех», а повышенная копия так и не заняла мьютекс.
"""

import ctypes
import time

import pytest

import cleaner_core as core

pytestmark = pytest.mark.skipif(not core.IS_WINDOWS,
                                reason="mutex exists on Windows only")


def _hold(name):
    """Занимает мьютекс и возвращает (kernel32, дескриптор)."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                      ctypes.c_wchar_p]
    handle = kernel32.CreateMutexW(None, 0, name)
    assert handle, "CreateMutexW failed"
    return kernel32, handle


def _release(kernel32, handle):
    kernel32.CloseHandle(ctypes.c_void_p(handle))


def test_free_mutex_is_not_taken_and_waits_full_timeout():
    name = r"Local\Swept.TestFreeInstance"
    started = time.monotonic()
    assert core.wait_for_other_instance(0.3, name) is False
    assert time.monotonic() - started >= 0.25


def test_taken_mutex_returns_true_without_waiting():
    name = r"Local\Swept.TestHeldInstance"
    kernel32, handle = _hold(name)
    try:
        started = time.monotonic()
        assert core.wait_for_other_instance(2.0, name) is True
        assert time.monotonic() - started < 1.0
    finally:
        _release(kernel32, handle)


def test_mutex_released_again_reads_as_free():
    name = r"Local\Swept.TestReleasedInstance"
    kernel32, handle = _hold(name)
    _release(kernel32, handle)
    assert core.wait_for_other_instance(0.2, name) is False


def test_zero_timeout_checks_once():
    name = r"Local\Swept.TestZeroTimeout"
    assert core.wait_for_other_instance(0.0, name) is False


def test_never_raises_on_bad_name():
    # Пустое имя мьютекса создать нельзя: функция обязана вернуть False,
    # а не уронить поток перезапуска исключением.
    assert core.wait_for_other_instance(0.2, "") is False
