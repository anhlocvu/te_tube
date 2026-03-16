## About the source code

Briefly, this is source code initialized from uv. It's not like regular Python; you need to use `winget install` or `pip install uv` to install uv.

### How to install via winget, which is recommended

Like me, if you don't have Python, you can install uv as follows:

Open cmd and enter

```cmd
winget install uv
```

Then, enter

```cmd
uv --version
```

to check. If it shows the uv version, it means you've succeeded.

### Adding libraries

It's very simple, just enter the command

```cmd
uv add <library name>
```

and it will add the package you requested.

For example

```cmd
uv add pygame
```

You will be able to add the library.

### Running code

It's very simple, you just need to enter the command

```cmd
uv run main.py
```

and the code will be executed.
