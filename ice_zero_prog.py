#!/usr/bin/env python2
##############################################################################
# ice_zero_prog.py
#             Copyright (c) Kevin M. Hubbard 2017 BlackMesaLabs
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Description:
#   This uses GPIO pins on a RaspPi to bit-bang SPI protocol to a FPGA PROM.
#
# Revision History:
# Ver   When       Who       What
# ----  --------   --------  ---------------------------------------------------
# 0.01  2017.01.22 khubbard  Creation. Reads PROM ID.
# 0.02  2017.01.28 khubbard  Writes Lattice bitfil to PROM now.
# 0.02  2017.01.29 khubbard  Bulk Erase Added.
# NOTE: Sector Erase not working yet.
##############################################################################

# pylint: disable=unnecessary-semicolon

import os
import sys
import time
from time import sleep

import RPi.GPIO as GPIO


class App:
  def __init__(self):
    return;

  def main(self):
    self.main_init();
#   self.main_loop();

  def main_init( self ):
    args = sys.argv + [None]*5;# args[0] is this scripts name
    self.arg0     = args[1];
    self.arg1     = args[2];
    self.spi_link = spi_link( platform="ice_zero_proto" );
    self.prom     = micron_prom( self.spi_link );

    file_name = self.arg0;
    if ( self.arg1 == None ):
      addr = 0x000000;
    else:
      addr = int( self.arg1, 16 );

    ret = 0

    mfr_id, dev_id, dev_cap = self.prom.read_id();
    print("=== Found %s %s %d MBytes" % (mfr_id, dev_id, dev_cap))

    print("=== Flashing %s to 0x%06x" % (os.path.basename(file_name), addr))
    self.prom.write_file_to_mem(file_name, addr)

    print("=== Verify first 512 bytes: ", end='')
    if self.prom.verify(file_name, addr, 512):
      print("OK")
    else:
      print("FAIL")
    ret = 1

    self.spi_link.close();
    return ret;

  def main_loop( self ):
    while( True ):
      pass;# Not used for this design
    return;


###############################################################################
# Class for bit banging to Micron SPI PROM connected to Lattice ICE40 FPGA
# The memory is organized as 256 (64KB) main sectors that are further divided
# into 16 subsectors each (4096 subsectors in total). The memory can be erased 
# one 4KB subsector at a time, 64KB sectors at a time, or as a whole. 
class micron_prom:
  def __init__ ( self, spi_link ):
    self.id           = 0x9f;# Read ID   
    self.wr           = 0x02;# Page Program
    self.rd           = 0x03;# Read Data
    self.rd_status    = 0x05;# Read Data
    self.wr_en        = 0x06;# Write Enable 
    self.wr_dis       = 0x04;# Write Disable
    self.relpd        = 0xab;# Release Deep PowerDown
    self.subsec_erase = 0x20;# Erase Sector
    self.sec_erase    = 0xd8;# Erase Sector
    self.bulk_erase   = 0xc7;# Bulk Erase Device
    self.spi_link = spi_link;
    self.sec_size = 64 * 2**10
    return;

  def read_id ( self ):
    miso_bytes = self.spi_link.xfer( [0x9F], 17 );# Micron READ_ID
    ( mfr_id, dev_id, dev_capacity ) = miso_bytes[0:3];
    if ( mfr_id == 0x20 ):
      mfr_id = "Micron";
    else:
      mfr_id = "%02x" % mfr_id;
    if ( dev_id == 0xBA ): 
      dev_id = "N25Q128A";
    else:
      dev_id = "%02x" % dev_id;
    dev_capacity = (2**dev_capacity) / (1024 * 1024 );
    return ( mfr_id, dev_id, dev_capacity );# 0x20, 0xBA, 0x18 == 128Mb

  def erase( self ):
    self.spi_link.xfer( [ self.wr_en ], 0 )
    self.spi_link.xfer( [ self.bulk_erase ], 0 )
    status = 0x01;# Loop until Status says erase is done
    while ( status & 0x01 != 0x00 ):
      status = self.spi_link.xfer( [ self.rd_status ], 1 )[0];
    self.spi_link.xfer( [ self.wr_dis ], 0 )
    return;

  def read_mem ( self, addr, num_bytes ):
    mosi_bytes = [ self.rd, 
                   ( addr & 0xFF0000 ) >> 16,
                   ( addr & 0x00FF00 ) >>  8,
                   ( addr & 0x0000FF ) >>  0 ];
    miso_bytes = self.spi_link.xfer( mosi_bytes, num_bytes );
    return miso_bytes;

  def verify(self, file_name, addr, byte_count = None):
    file_in = open(file_name, 'r')
    file_bytes = file_in.read()
    file_in.close()

    if not byte_count:
      byte_count = len(file_bytes)

    miso_bytes = self.read_mem( addr, byte_count);
    for index, byte in enumerate(miso_bytes):
      expected = ord(file_bytes[index])
      if byte != expected:
        print("Mismatch at 0x%06x: read 0x%02x, expected 0x%02x" % (addr + index, byte, expected))
        return False

    return True

  def _addr_to_sector(self, addr):
    return (int(addr / self.sec_size))

  def _sector_to_addr(self, sector):
    return (sector * self.sec_size)

  def erase_sector_at_addr(self, addr):
    sector = self._addr_to_sector(addr)
    sector_start = self._sector_to_addr(sector)
    sector_end = self._sector_to_addr(sector + 1) - 1

    print("== Erase sector %d (0x%06x - 0x%06x)" % (sector, sector_start, sector_end) )

    # Write enable
    self.spi_link.xfer( [ self.wr_en ], 0 )

    mosi_bytes = [ self.sec_erase,
                   ( addr & 0xFF0000 ) >> 16,
                   ( addr & 0x00FF00 ) >>  8,
                   ( addr & 0x0000FF ) >>  0 ];
    # Erase the sector
    self.spi_link.xfer( mosi_bytes, 0 )

    # Write disable
    self.spi_link.xfer( [ self.wr_dis ], 0 )

    status = 0x01;# Loop until Status says erase is done
    while ( status & 0x01 != 0x00 ):
      status = self.spi_link.xfer( [ self.rd_status ], 1 )[0];

  def erase_sector(self, n):
    self.erase_sector_at_addr(self._sector_to_addr(n))

  def write_file_to_mem( self, file_name, addr ):
    # Great example of reading a binary file
    file_in = open ( file_name, 'r' );
    file_bytes = file_in.read();
    file_in.close()

    total_bytes = len( file_bytes );
    erased_sectors = []

    perc = 0; xferd = 0;
    while( len( file_bytes ) > 0 ):
      if ( ( 100.0*float(xferd) / float(total_bytes) ) > perc ):
        print("%d%%" % (perc) );
        perc += 10;

      sector = self._addr_to_sector(addr)
      if not sector in erased_sectors:
        self.erase_sector_at_addr(addr)
        erased_sectors.append(sector)

      # Grab 256 bytes at a time
      if ( len( file_bytes ) > 256 ):
        xfer_bytes = file_bytes[0:256];
        file_bytes = file_bytes[256:];
      else:
        xfer_bytes = file_bytes[0:];
        file_bytes = [];
      mosi_bytes = [ self.wr, 
                     ( addr & 0xFF0000 ) >> 16,
                     ( addr & 0x00FF00 ) >>  8,
                     ( addr & 0x0000FF ) >>  0 ];
      for byte in xfer_bytes:
        mosi_bytes += [ ord( byte )];
      self.spi_link.xfer( [ self.wr_en ], 0 )
      self.spi_link.xfer( mosi_bytes, 0 ); # Write 256 bytes
      self.spi_link.xfer( [ self.wr_dis ], 0 )
      status = 0x01;# Loop until Status says write is done
      while ( status & 0x01 != 0x00 ):
        status = self.spi_link.xfer( [ self.rd_status ], 1 )[0];
      addr += 256; xferd += 256;
    return;

  def write_mem ( self, addr, num_bytes ):
    mosi_bytes = [ self.rd, 
                   ( addr & 0xFF0000 ) >> 16,
                   ( addr & 0x00FF00 ) >>  8,
                   ( addr & 0x0000FF ) >>  0 ];
    miso_bytes = self.spi_link.xfer( mosi_bytes, num_bytes );
    return miso_bytes;

  def close( self ):
    return;


###############################################################################
# Class for bit banging to Micron SPI PROM connected to Lattice ICE40 FPGA
class spi_link:
  def __init__ ( self, platform ):
    try:
      import RPi.GPIO as GPIO;
    except:
      raise RuntimeError("ERROR: Unable to import RaspPi RPi.GPIO module");

    if ( platform == "ice_zero_proto" ):
      GPIO.setmode(GPIO.BOARD);
      self.pin_rst_l = 37;
      self.pin_clk   = 36;
      self.pin_cs_l  = 32;
      self.pin_miso  = 31;
      self.pin_mosi  = 33;
      self.pin_done  = 39;
    else:
      raise RuntimeError("ERROR: Unknown platform " + platform );

    GPIO.setup( self.pin_rst_l, GPIO.OUT, initial = GPIO.LOW );
    GPIO.setup( self.pin_cs_l , GPIO.OUT, initial = GPIO.HIGH );
    GPIO.setup( self.pin_clk  , GPIO.OUT, initial = GPIO.LOW  );
    GPIO.setup( self.pin_mosi , GPIO.OUT, initial = GPIO.LOW  );
    GPIO.setup( self.pin_miso , GPIO.IN                       );
    return;

  def close( self ):
    GPIO.setup( self.pin_cs_l , GPIO.IN );
    GPIO.setup( self.pin_clk  , GPIO.IN );
    GPIO.setup( self.pin_mosi , GPIO.IN );
    GPIO.setup( self.pin_rst_l, GPIO.IN );
    return;

  def xfer( self, mosi_bytes, miso_bytes_len ):
    GPIO.output( self.pin_cs_l , GPIO.LOW);# Assert Chip Select
    miso_bytes = [];
    for each_byte in mosi_bytes:
      shift_reg = each_byte;
      for _ in range(0,8,1):
        bit = 0x80 & shift_reg;
        if ( bit == 0x00 ):
          GPIO.output( self.pin_mosi , GPIO.LOW);
        else:
          GPIO.output( self.pin_mosi , GPIO.HIGH);
        GPIO.output( self.pin_clk , GPIO.HIGH);
        GPIO.output( self.pin_clk , GPIO.LOW );
        shift_reg = ( shift_reg << 1 );
    for _ in range(0, miso_bytes_len):
      shift_reg = 0x00;
      for _ in range(0,8,1):
        bit = GPIO.input( self.pin_miso );
        GPIO.output( self.pin_clk , GPIO.HIGH);
        GPIO.output( self.pin_clk , GPIO.LOW );
        shift_reg = (bit     ) + (shift_reg << 1);
      miso_bytes += [ shift_reg ];   
    GPIO.output( self.pin_cs_l , GPIO.HIGH);# Assert Chip Select
    return miso_bytes;


###############################################################################
app = App();
sys.exit(app.main());
