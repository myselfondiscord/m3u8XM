
# M3U8 XM

A fork of a WIP script that converts SiriusXM's web app into a M3U8 file, but with metadata added


Credits to [andrew0](https://github.com/andrew0) for the basis of this script.

## Features

- Automatic login
- Creates a full channel playlist
- Support for channel logos & genre filtering
EPG coming soon
- Metadata
## Run Locally

Clone the project

```bash
  git clone https://github.com/myselfondiscord/m3u8XM
```

Go to the project directory

```bash
  cd m3u8XM
```

### Add your config file
rename ``config.example.ini`` to ``config.ini`` and edit the email/password to your SXM account.

Start the server

```bash
  python3 sxm.py
```


## License

[MIT](https://choosealicense.com/licenses/mit/)

This project is not affiliated with SiriusXM
