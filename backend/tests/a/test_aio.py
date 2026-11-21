import asyncio

import pytest

from app.geo.aio import wait_shared


def test_wait_shared_times_out_without_cancelling_and_without_log(caplog):
    async def run():
        async def slow_fail():
            await asyncio.sleep(0.05)
            raise RuntimeError("late upstream failure")

        task = asyncio.get_running_loop().create_task(slow_fail())
        task.add_done_callback(lambda t: t.exception())   # as the shared tasks in dem/soilgrids do
        with pytest.raises(asyncio.TimeoutError):
            await wait_shared(task, timeout=0.01)
        assert not task.done()                             # still running in the background
        await asyncio.sleep(0.1)
        assert isinstance(task.exception(), RuntimeError)

    asyncio.run(run())
    assert "shielded future" not in caplog.text


def test_wait_shared_returns_result():
    async def run():
        task = asyncio.get_running_loop().create_task(asyncio.sleep(0, result=7))
        return await wait_shared(task, timeout=1)

    assert asyncio.run(run()) == 7
