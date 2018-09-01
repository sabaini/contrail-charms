import base64
import json
import os
import platform
from subprocess import check_call, check_output

from charmhelpers.core.hookenv import config, log
from charmhelpers.core.host import service_restart
from charmhelpers.fetch import apt_install, apt_update

config = config()

DOCKER_PACKAGES = ["docker.ce", "docker-compose"]
DOCKER_CLI = "/usr/bin/docker"
DOCKER_COMPOSE_CLI = "docker-compose"


def install():
    apt_install(["apt-transport-https", "ca-certificates", "curl",
                 "software-properties-common"])
    cmd = ["/bin/bash", "-c",
           "set -o pipefail ; curl -fsSL --connect-timeout 10 "
           "https://download.docker.com/linux/ubuntu/gpg "
           "| sudo apt-key add -"]
    check_output(cmd)
    dist = platform.linux_distribution()[2].strip()
    cmd = ("add-apt-repository "
           "\"deb [arch=amd64] https://download.docker.com/linux/ubuntu "
           + dist + " stable\"")
    check_output(cmd, shell=True)
    apt_update()
    apt_install(DOCKER_PACKAGES)


def _load_json_file(filepath):
    try:
        with open() as f:
            return json.load(f)
    except Exception as e:
        pass
    return dict()


def _save_json_file(filepath, data):
    with open(file, "w") as f:
        json.dump(data, f)


def apply_insecure():
    if not config.get("docker-registry-insecure"):
        return
    docker_registry = config.get("docker-registry")

    log("Re-configure docker daemon")
    dc = _load_json_file("/etc/docker/daemon.json")

    cv = dc.get("insecure-registries", list())
    if docker_registry in cv:
        return
    cv.append(docker_registry)
    dc["insecure-registries"] = cv

    _save_json_file("/etc/docker/daemon.json", dc)

    log("Restarting docker service")
    service_restart('docker')


def login():
    # 'docker login' doesn't work simply on Ubuntu 18.04. let's hack.
    login = config.get("docker-user")
    password = config.get("docker-password")
    if not login or not password:
        return

    auth = base64.b64encode("{}:{}".format(login, password))
    docker_registry = config.get("docker-registry")
    config_path = os.path.join(os.path.expanduser("~"), ".docker/config.json")
    data = _load_json_file(config_path)
    data.setdefault("auths", dict())[docker_registry] = {"auth": auth}
    _save_json_file(config_path, data)


def cp(name, src, dst):
    check_call([DOCKER_CLI, "cp", name + ":" + src, dst])


def execute(name, cmd, shell=False):
    cli = [DOCKER_CLI, "exec", name]
    if isinstance(cmd, list):
        cli.extend(cmd)
    else:
        cli.append(cmd)
    if shell:
        output = check_output(' '.join(cli), shell=True)
    else:
        output = check_output(cli)
    return output.decode('UTF-8')


def get_image_id(image, tag):
    registry = config.get("docker-registry")
    return "{}/{}:{}".format(registry, image, tag)


def pull(image, tag):
    check_call([DOCKER_CLI, "pull", get_image_id(image, tag)])


def compose_run(path):
    check_call([DOCKER_COMPOSE_CLI, "-f", path, "up", "-d"])


def remove_container_by_image(image):
    output = check_output([DOCKER_CLI, "ps", "-a"]).decode('UTF-8')
    containers = [line.split() for line in output.splitlines()][1:]
    for cnt in containers:
        if len(cnt) < 2:
            # bad string. normal output contains 6-7 fields.
            continue
        cnt_image = cnt[1]
        index = cnt_image.find(image)
        if index < 0 or (index > 0 and cnt_image[index - 1] != '/'):
            # TODO: there is a case when image name just a prefix...
            continue
        check_call([DOCKER_CLI, "rm", cnt[0]])


def run(image, tag, volumes, remove=False):
    image_id = get_image_id(image, tag)
    args = [DOCKER_CLI, "run"]
    if remove:
        args.append("--rm")
    args.extend(["-i", "--network", "host"])
    for volume in volumes:
        args.extend(["-v", volume])
    args.extend([image_id])
    check_call(args)


def get_contrail_version(image, tag, pkg="python-contrail"):
    image_id = get_image_id(image, tag)
    return check_output([DOCKER_CLI,
        "run", "--rm", "--entrypoint", "rpm", image_id,
        "-q", "--qf", "%{VERSION}-%{RELEASE}", pkg]).decode("UTF-8").rstrip()
