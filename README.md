# ice_zero_prog
Python for BitBanging SPI PROM on IceZero FPGA board from RaspPi GPIO pins

## Usage

```
ice_zero_prog.py <file.bin> [<dest_addr>]
```

### Using StdIn - Remote

If you pass `-` as the filename the script will read the Flash image from the *STDIN*:

`ice_zero_prog.py - [<dest_addr>] < <file.bin>`

Thus you can start it remotely:

```
ssh pi@your.r.pi.ip ./ice_zero_prog/ice_zero_prog.py - < file.bin
```

Where
- this repository is cloned into the *Home*-Directory of the *pi*-user on a *RaspberryPi*
- `file.bin` is on your *Host* machine
