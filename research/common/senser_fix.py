"""Patched pull: fixes pmca's sendSenserPacket stream desync on PID 0x0336.

pmca line ~870 does an extra `driver.read(SenserMinSize)` padding read after
every chunk whose length is 512-aligned. On the 0x0336 senser device minSize is
forced to 0, so that padding read is NOT part of the protocol -- it swallows
0x8000 (32768) bytes of real payload per transfer and desyncs the stream, which
is why every pull returned exactly (size - 32768) and the bytes were scrambled.

This re-implements the read loop without the bogus padding read.
"""
import sys, io, os, hashlib
from pmca.usb.sony import SonySenserDevice

_orig = SonySenserDevice.sendSenserPacket

def _fixed(self, pFunc, data, oData=None):
    while data != b'':
        header = self.SenserPacketHeader.pack(size=len(data), pFunc=pFunc,
                                              sequence=self._sequence, version=0,
                                              miconType=0, offsetType=0, response=0)
        self.driver.write(header + data[:self.SenserMaxSize])
        data = data[self.SenserMaxSize:]

    outData = io.BytesIO() if oData is None else oData
    pid = self.driver.getId()[1]
    minSize = 0 if pid == 0x0336 else self.SenserMinSize
    while True:
        l = max(minSize - self.SenserPacketHeader.size, 0)
        d = self.driver.read(self.SenserPacketHeader.size + l)
        header = self.SenserPacketHeader.unpack(d)
        if header.sequence != self._sequence:
            raise Exception('Wrong senser sequence')
        outData.write(d[self.SenserPacketHeader.size:])
        done = l

        dataLen = min(header.size, self.SenserMaxSize)
        chunkLen = self.SenserChunkSize - minSize
        while done < dataLen:
            l = min(dataLen - done, chunkLen)
            outData.write(self._readAll(l))
            done += l
            # ONLY do the alignment/padding read when the device actually
            # uses a non-zero minSize. With minSize==0 (PID 0x0336) this
            # extra read eats real data.
            if minSize and not (l & (self.SenserMinSize - 1)):
                self.driver.read(self.SenserMinSize)
            chunkLen = self.SenserChunkSize
        if header.size <= self.SenserMaxSize:
            break
    self._sequence += 1
    return header.response, outData.getvalue() if oData is None else None

SonySenserDevice.sendSenserPacket = _fixed
