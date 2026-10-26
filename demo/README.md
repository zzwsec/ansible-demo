# Semaphore 文件更新演练

用假的应用和专用 systemd 服务，演练：上传压缩包 → 传递路径变量 → 复制到目标主机并解压 → 读取 unit 的 WorkingDirectory → 停服 → 覆盖文件 → 启动 → 校验。

这是独立示例，不依赖原更新项目；模拟的是 UAT App 更新后自动启动的流程。它不模拟生产环境的“全量更新后保持停止”，也不包含 Lua 热更。

## 文件

| 文件 | 用途 |
|---|---|
| `setup-demo.yml` | 在被管理主机上创建 v1 假应用、文本文件和 unit，并启动 |
| `update-demo.yml` | 使用你上传到 Semaphore 的 v2 更新包进行停机更新和验证 |
| `cleanup-demo.yml` | 演练结束后移除专用服务和目录 |
| `create-package.py` | 用标准库生成演练更新包，不需要编译 |
| `update-demo-v2.tar.gz` | 本地套件已附带；从 Git 仓库获取时运行生成脚本即可 |
| `inventory.example.ini` | 示例主机清单，连接地址按实际修改 |

目标主机需要 Linux、systemd、Python 3、GNU tar、gzip 和 GNU sleep。使用 root SSH 凭据，或者具备对应 sudo 权限的账号。服务不监听任何网络端口，也不会设置为开机启动。

## 1. 将剧本加入 Git 仓库

将三个 `.yml` 和 `create-package.py` 放入仓库，例如：

```text
demo/
├── setup-demo.yml
├── update-demo.yml
├── cleanup-demo.yml
└── create-package.py
```

Git 保存剧本和生成脚本；更新包单独上传，不放进 Git。

Inventory 可以继续使用已有清单。第一次测试时，把模板的 Limit 固定为一台测试主机别名，例如 `uat_node1_game1`。本示例通过 SSH 在这台被管理主机上创建 unit；不要求 Semaphore 容器本身运行 systemd。

## 2. 运行初始化模板

创建 Ansible Playbook 模板：

- 名称：`Demo 初始化`
- 剧本文件路径：`demo/setup-demo.yml`
- Inventory：选择能连接测试主机的清单和凭据
- Limit：`uat_node1_game1`，或你的实际测试主机别名
- CLI args：`-v`（可选）
- Skip Galaxy install：勾选

初始化不需要 `update_artifact_path` 或 `update_exec_type`。成功后，目标主机上会出现：

```text
/etc/systemd/system/semaphore-update-demo.service
/opt/semaphore-update-demo/
├── .semaphore-demo
├── p8_app_server         # Shell 脚本模拟的应用，版本 demo-v1
├── message.txt           # 待更新的文本文件
└── running-version.txt   # 实际启动的应用写入 demo-v1
```

unit 的 `WorkingDirectory` 是 `/opt/semaphore-update-demo`。重新运行初始化会把演练应用重置为 v1 并重启演练服务。

## 3. 上传 v2 更新包

先在 Docker 宿主机创建 `/srv/update-inbox`，向现有 Semaphore 服务的 `volumes` 列表追加挂载，保留原挂载项：

```yaml
services:
  semaphore:
    volumes:
      - /srv/update-inbox:/srv/update-inbox:ro
```

用 `docker compose up -d semaphore` 应用挂载。服务名按实际修改。如果任务由其他 Runner 执行，需要将相同目录提供给真正运行任务的 Runner / 执行容器。

如果从 Git 仓库获取演练文件，先在电脑上生成测试包：

```bash
python demo/create-package.py
```

解压本地套件的用户已有测试包，可跳过生成。把 `update-demo-v2.tar.gz` 用 SFTP 上传到宿主机 `/srv/update-inbox/`，或者从电脑执行：

```bash
scp ./demo/update-demo-v2.tar.gz YOUR_SSH_USER@Docker宿主机IP:/srv/update-inbox/
```

确认上传完成，并且容器中的任务用户能够读取：

```bash
docker compose exec semaphore sh -c 'test -r /srv/update-inbox/update-demo-v2.tar.gz && echo readable'
```

演练包内的结构是：

```text
app/
├── p8_app_server   # 可执行 Shell 脚本，启动时写入 demo-v2，之后保持运行
└── message.txt     # 这是通过 demo-v2 更新包分发的新文件。
```

不要在传输或更新过程中覆盖这个文件。

## 4. 运行更新模板

创建另一个 Ansible Playbook 模板：

- 名称：`Demo 文件更新`
- 剧本文件路径：`demo/update-demo.yml`
- Inventory、Limit：与初始化模板一致
- CLI args：`-v`（可选）
- Skip Galaxy install：勾选

在变量组的“额外变量”中添加：

```json
{
  "update_artifact_path": "/srv/update-inbox/update-demo-v2.tar.gz"
}
```

类型选 String。也可以在模板中添加同名、必填的调查变量，传递方式选 Extra variable，在启动任务时填写；两种方式选一种。

这是通过 `-e` / `--extra-vars` 传入的包路径。不要放在“环境变量”中。本示例专门测试 App 更新，因此不需要 `update_exec_type`。

任务会先在 Semaphore 执行容器中检查更新包，再把包传到被管理主机解压；`remote_src: true` 只用于后续在被管理主机本地复制解压后的文件。

最后应看到：

```yaml
服务名称: semaphore-update-demo.service
服务状态: active
运行版本: demo-v2
更新后文件内容: 这是通过 demo-v2 更新包分发的新文件。
```

也可 SSH 到目标主机检查：

```bash
systemctl status semaphore-update-demo.service --no-pager
cat /opt/semaphore-update-demo/running-version.txt
cat /opt/semaphore-update-demo/message.txt
```

有 `changed` 是正常的：这次确实创建或替换了文件，并执行了服务停启。初始程序、更新程序都会写入运行版本，验证时会等待新进程启动并核对版本和文件内容。

## 5. 清理演练

新建模板执行 `demo/cleanup-demo.yml`，使用相同 Inventory 和 Limit。它只停止并删除 `semaphore-update-demo.service` 及 `/opt/semaphore-update-demo`；宿主机的上传包保留，按需手动删除。

## 命令行等效操作

将示例清单地址替换为实际测试主机后，在当前目录执行：

```bash
ansible-playbook -i inventory.example.ini setup-demo.yml --limit demo_node

ansible-playbook -i inventory.example.ini update-demo.yml --limit demo_node \
  -e update_artifact_path=/srv/update-inbox/update-demo-v2.tar.gz -v

ansible-playbook -i inventory.example.ini cleanup-demo.yml --limit demo_node
```

## 验证范围

交付时检查了 YAML 结构、更新包目录与脚本内容、脚本可执行位以及最终 ZIP 内容。本机环境没有 Linux systemd 或可用的 Ansible 执行环境，尚未实际启动演练服务；首次运行请选单台测试主机。

## 参考

- [Ansible unarchive：默认从控制端复制压缩包到目标再解压](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/unarchive_module.html)
- [Ansible systemd_service](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/systemd_service_module.html)
