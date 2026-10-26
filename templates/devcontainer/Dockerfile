# aidd dev container: a place to run coding agents with outbound traffic denied by default.
# A starting point, not a guarantee: aidd itself sandboxes nothing (docs/HOW-TO.md, "run agents in a sandbox").
#
# The egress allow-list is baked into the image at build time, into a root-owned file, so nothing running inside the
# container (an agent included) can widen it: change it in .devcontainer/devcontainer.json (`build.args`) and rebuild.
# .devcontainer/** is a protected path, so that change goes through the gate as a major change.

# The interpreter aidd's GitLab template pins, by the digest of its multi-arch index. Update the tag and digest together.
FROM python:3.14.7-trixie@sha256:0876e54cf728d89fd9d0fdaf5837b9ee879ea5fbbd6fd0cddbe5eb0cce3f5f9e

# The hosts the container may reach, besides DNS and loopback (see init-firewall.sh). Space-separated host names.
ARG CODE_HOST=github.com
ARG MODEL_API_HOST=api.anthropic.com
ARG PACKAGE_HOSTS="pypi.org files.pythonhosted.org registry.npmjs.org proxy.golang.org sum.golang.org index.crates.io static.crates.io"
ARG EXTRA_HOSTS=""
ARG USERNAME=dev
ARG USER_UID=1000

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git iptables ipset iproute2 jq sudo \
 && rm -rf /var/lib/apt/lists/*

# The allow-list, one host per line, readable by everyone and writable only by root.
RUN mkdir -p /etc/aidd-egress \
 && printf '%s\n' "$CODE_HOST" "$MODEL_API_HOST" $PACKAGE_HOSTS $EXTRA_HOSTS | awk 'NF' | sort -u > /etc/aidd-egress/allowed-hosts \
 && printf '%s\n' "$CODE_HOST" > /etc/aidd-egress/code-host \
 && chmod 0644 /etc/aidd-egress/allowed-hosts /etc/aidd-egress/code-host

COPY init-firewall.sh /usr/local/sbin/aidd-init-firewall
RUN chmod 0755 /usr/local/sbin/aidd-init-firewall

# A non-root user who may run the firewall script as root, and nothing else as root. The script takes no arguments
# and reads no environment, so running it again only re-applies the same list.
RUN useradd --create-home --shell /bin/bash --uid "$USER_UID" "$USERNAME" \
 && printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/aidd-init-firewall\n' "$USERNAME" > /etc/sudoers.d/aidd-firewall \
 && chmod 0440 /etc/sudoers.d/aidd-firewall

USER $USERNAME
ENV PATH="/home/${USERNAME}/.local/bin:${PATH}"
WORKDIR /workspace
