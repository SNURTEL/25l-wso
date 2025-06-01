import asyncio

import wso.config as config


async def send_msg_to_daemon(message: str) -> str:
    reader, writer = await asyncio.open_connection(config.SERVER_HOST, config.SERVER_PORT)

    writer.write(message.encode())
    await writer.drain()

    status = await reader.readline()
    if status.decode().strip() != "OK":
        data = await reader.read(256 * 1024)
        raise RuntimeError(f"Daemon returned error: {status.decode().strip()}, {data.decode().strip()}")
    data = await reader.read()

    writer.close()
    await writer.wait_closed()
    return data.decode().strip()


def send_msg(msg: str) -> str:
    return asyncio.run(send_msg_to_daemon(msg))
