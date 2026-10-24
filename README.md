# eyeokuri

Read your visual novel hands-free. `eyeokuri` watches your webcam and advances the text when you blink, so you can keep your hands off the keyboard and mouse.

- **Blink to advance.** A blink sends `Enter` to the game. You can send any other key, a key combination such as `Ctrl+S`, a left click or a scroll-down instead.
- **Shake your head to pause.** Shake again to resume, for example when you look away or answer the phone.
- **Make it fit you.** A gesture wizard learns your blink from a few practice takes. You can also edit each gesture's thresholds and timing in its gesture window.
- **Private.** It needs only a webcam. Frames are processed in memory on your PC and never stored or sent anywhere.

**[Read the guide](https://lulalala.github.io/eyeokuri/)** for how to use the app.

## Install

Download `eyeokuri-setup.exe` from the [latest release](https://github.com/lulalala/eyeokuri/releases/latest) and run it. It installs eyeokuri for your Windows account without administrator rights and adds it to the Start menu. Windows might warn about an unknown publisher because the app is not signed; select **More info**, then **Run anyway**.

The installer includes the face model, so eyeokuri works offline. The release also has `eyeokuri-windows.zip`, the same app without an installer: unzip it and run `eyeokuri.exe`. Then follow [Get started](https://lulalala.github.io/eyeokuri/guide/getting-started/).

### Install from source

Requires Python 3.11+.

```sh
python -m venv .venv
.venv\Scripts\activate
pip install -e .
eyeokuri-gui                       # loads config.toml if it exists
eyeokuri-gui --config my.toml      # load and save another file
```

The face landmark model (~4 MB) is downloaded on first run. That download is the only network access eyeokuri makes.

## Documentation

- [Get started](https://lulalala.github.io/eyeokuri/guide/getting-started/): first run, default gestures and the blink timing.
- [Use the main window](https://lulalala.github.io/eyeokuri/guide/main-window/), [edit a gesture](https://lulalala.github.io/eyeokuri/guide/edit-a-gesture/), [set up a gesture with the wizard](https://lulalala.github.io/eyeokuri/guide/gesture-wizard/) and [change camera and feedback settings](https://lulalala.github.io/eyeokuri/guide/config-window/).
- [Edit gestures in the config file](https://lulalala.github.io/eyeokuri/guide/config-file/) and [`config.example.toml`](config.example.toml), which lists every field.
- [Command line](docs/command-line.md): run without a window, `--set`, the preview window and logging.
- [Development](docs/development.md): set up, test and build; [research notes](docs/research.md).

## License

eyeokuri is licensed under the [Apache License 2.0](LICENSE). The third-party material that the Windows build includes is listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
