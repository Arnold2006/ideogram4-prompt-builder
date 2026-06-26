module.exports = {
  version: "5.0",
  title: "Ideogram 4 Prompt Builder",
  description: "Desktop GUI for building Ideogram 4 JSON captions with a prompt library and ComfyUI integration",
  icon: "eng-vlack.png",
  menu: async (kernel, info) => {
    const installed = info.exists("env")
    const running = {
      install: info.running("install.js"),
      start:   info.running("start.js"),
      update:  info.running("update.js"),
      reset:   info.running("reset.js"),
    }

    if (running.install) {
      return [{
        default: true,
        icon: "fa-solid fa-plug",
        text: "Installing\u2026",
        href: "install.js",
      }]
    }

    if (running.start) {
      return [{
        default: true,
        icon: "fa-solid fa-terminal",
        text: "Running",
        href: "start.js",
      }]
    }

    if (running.update) {
      return [{
        default: true,
        icon: "fa-solid fa-terminal",
        text: "Updating\u2026",
        href: "update.js",
      }]
    }

    if (running.reset) {
      return [{
        default: true,
        icon: "fa-solid fa-terminal",
        text: "Resetting\u2026",
        href: "reset.js",
      }]
    }

    if (installed) {
      return [
        {
          default: true,
          icon: "fa-solid fa-play",
          text: "Launch",
          href: "start.js",
        },
        {
          icon: "fa-solid fa-rotate",
          text: "Update",
          href: "update.js",
        },
        {
          icon: "fa-solid fa-plug",
          text: "Re-install",
          href: "install.js",
        },
        {
          icon: "fa-regular fa-circle-xmark",
          text: "<div><strong>Reset</strong><div>Remove venv and start fresh</div></div>",
          href: "reset.js",
          confirm: "Are you sure you want to reset? This will delete the virtual environment."
        }
      ]
    }

    return [{
      default: true,
      icon: "fa-solid fa-plug",
      text: "Install",
      href: "install.js",
    }]
  }
}
