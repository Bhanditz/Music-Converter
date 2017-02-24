# Music Converter
Converts entire library to specified format, ignoring files that were previously converted. It currently only works in Unix-like systems due to glob, but it shouldn't be hard to adapt for Windows.

## Usage
Pick one of the audiotools.AVAILABLE_TYPES from http://audiotools.sourceforge.net/programming/audiotools.html and input it as a string to the MusicConverter object.
```python
archive_path = ''
portable_path = ''

converter = MusicConverter(archive_path, portable_path, 'OpusAudio')
converter.run()
```

AACAudio, OggFlacAudio, and ShortenAudio appear to be unsupported in Audiotools despite being listed in the documentation. If you find these work for you, you should uncomment those lines in the source. Here are the formats currently supported without requiring any modification:
- AiffAudio
- ALACAudio
- AuAudio
- FlacAudio
- M4AAudio
- MP3Audio
- MP2Audio
- OpusAudio
- SpeexAudio
- VorbisAudio
- WaveAudio
- WavPackAudio
