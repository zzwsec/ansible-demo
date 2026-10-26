"""生成独立演练使用的 tar.gz 更新包。"""

from io import BytesIO
from pathlib import Path
import tarfile


destination = Path(__file__).with_name('update-demo-v2.tar.gz')
files = {
    'app/p8_app_server': (
        b"#!/bin/sh\nset -eu\nprintf '%s\\n' 'demo-v2' > running-version.txt\nexec sleep infinity\n",
        0o755,
    ),
    'app/message.txt': (
        '这是通过 demo-v2 更新包分发的新文件。\n'.encode('utf-8'),
        0o644,
    ),
}

with tarfile.open(destination, 'w:gz', format=tarfile.USTAR_FORMAT) as archive:
    app = tarfile.TarInfo('app')
    app.type = tarfile.DIRTYPE
    app.mode = 0o755
    archive.addfile(app)

    for name, (content, mode) in files.items():
        member = tarfile.TarInfo(name)
        member.size = len(content)
        member.mode = mode
        archive.addfile(member, BytesIO(content))

print(f'演练更新包已生成：{destination}')
