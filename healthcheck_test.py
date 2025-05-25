import asyncio
import errno
import sys


async def healthcheck(host: str, port: int) -> bool:
    timeout = 1.0  # seconds
    try:
        future = asyncio.open_connection(host, port)
        _, writer = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"Healthcheck failed: timeout after {timeout}s while connecting to {host}:{port}")
        return False
    except OSError as e:
        _errno, msg = e.args
        print(
            f"Healthcheck failed: [Error {_errno}] {errno.errorcode.get(_errno, '??? Unknown error')}: {msg} while connecting to {host}:{port}"
        )
        return False
    writer.close()
    return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python healthcheck_test.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    is_healthy = asyncio.run(healthcheck(host, port))
    if not is_healthy:
        print(f"Healthcheck failed: {host}:{port} is not reachable.")
        sys.exit(1)
    else:
        print(f"Healthcheck successful: {host}:{port} is reachable.")
