module.exports = {
  daemon: false,
  run: [
    {
      method: "shell.run",
      params: {
        venv: "env",
        message: "python ideogram_prompt_builder.py"
      }
    }
  ]
}
