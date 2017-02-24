import re
import os
import sys
import glob
import shutil
import audiotools
import multiprocessing


class JobTracker:
	""" Object used to manage and document progress of multiprocessing pool. """
	def __init__(self, total=0):
		self.prog, self.active, = 0, []
		self.total = total
		self.procs = multiprocessing.cpu_count()

	def show_state(self):
		""" Lists all jobs currently in progress with a progress bar. Updates
		same region in console.
		Arguments: None
		Returns: None
		Side effects:
			Sends message to stdout.
		"""
		done = self.prog/self.total
		width = int(os.popen('stty size', 'r').read().split()[1])
		paths = '\n'.join((
			self.active + ['' for i in range(self.procs - len(self.active))]
		)[::-1])
		fill = int(done * width)
		blank = width - fill
		if fill > blank:
			fill = fill - 6
		else:
			blank = blank - 6
		bar = '\r{}{} {} %'.format('█' * fill, '░' * blank, int(done * 100))
		lines = min(len(self.active) - self.prog, self.procs)
		sys.stdout.write('\033[F'*self.procs + (' ' * width + '\n') * self.procs)
		sys.stdout.write('\033[F'*self.procs + paths + '\n' + bar)
		sys.stdout.flush()

	def job_done(self, rm):
		""" Takes note that a job has completed and refreshes the display.
		Required arguments:
			rm -- String representation for completed job
		Returns: None
		Side effects:
			Increments progress counter by one.
			Removes rm from list of active jobs.
			Sends new string to stdout.
		"""
		self.prog += 1
		self.active.remove(rm)
		self.show_state()

	def job_start(self, new):
		""" Takes note that a job has started and refreshes the display.
		Required arguments:
			new -- String representation for newly started job.
		Returns: None
		Side effects:
			Adds new to list of active jobs.
			Sends new string to stdout.
		"""
		self.active.append(new)
		self.show_state()

	def run(self, fun, args_list):
		""" Creates multiprocessing pool to create a process to execute
		a given function for every provided set of arguments.
		Required arguments:
			fun -- function to execute.
			args_list -- list of arguments (or lists of arguments) for fun.
		Returns: None
		Side effects:
			Adds new to list of active jobs.
			Sends new string to stdout.
			Side effects of fun.
		"""
		print('\n' * (self.procs - 1))
		with multiprocessing.Pool() as pool:
			for match in args_list:
				if len(self.active) == self.procs:
					result.wait()
				self.job_start(match[2])
				result = pool.apply_async(fun, match, callback=self.job_done)
			result.get()


class MusicConverter(JobTracker):
	""" Object used to convert music library into another format. """
	# Commented out a few that didn't work.
	formats = {
		#'AACAudio': (audiotools.AACAudio, 'm4a'),
		'AiffAudio': (audiotools.AiffAudio, 'aiff'),
		'ALACAudio': (audiotools.ALACAudio, 'alac'),
		'AuAudio': (audiotools.AuAudio, 'au'),
		'FlacAudio': (audiotools.FlacAudio, 'flac'),
		'M4AAudio': (audiotools.M4AAudio, 'm4a'),
		'MP3Audio': (audiotools.MP3Audio, 'mp3'),
		'MP2Audio': (audiotools.MP2Audio, 'mp2'),
		#'OggFlacAudio': (audiotools.OggFlacAudio, 'ogg'),
		'OpusAudio': (audiotools.OpusAudio, 'opus'),
		#'ShortenAudio': (audiotools.ShortenAudio, 'shn'),
		'SpeexAudio': (audiotools.SpeexAudio, 'spx'),
		'VorbisAudio': (audiotools.VorbisAudio, 'ogg'),
		'WaveAudio': (audiotools.WaveAudio, 'wav'),
		'WavPackAudio': (audiotools.WavPackAudio, 'wv')
	}
	music_ext = [
		'wav', 'aiff', 'wma', 'alac', 'spx', 'wv', 'ape',
		'mp2', 'opus', 'shn', 'flac', 'mp3', 'au', 'm4a', 'ogg'
	]
	image_ext = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tif']

	def __init__(self, archive_path, portable_path, out_format, quality=None):
		super().__init__()
		self.archive_path = archive_path
		self.portable_path = portable_path
		self.matches = []
		self.portable = set(glob.glob(portable_path + '/**', recursive=True))
		self.regex_music = self.regext(self.music_ext)
		self.regex_image = self.regext(self.image_ext)
		self.out_format, self.out_ext = self.formats[out_format]
		self.quality = quality

	def regext(self, t):
		""" Converts a list of strings into a regular expression that
		will match files using it as a file extension.
		Required arguments:
			t -- List or tuple of file extension strings
		Returns:
			Regex with 3 groups touching the end of the string: (1)(2)(3)$
				1. Archive path.
				2. Any text followed by a dot.
				3. Any of the extensions in t.
		"""
		return re.compile(
			'({})(.*\.)({})$'.format(self.archive_path, '|'.join(t))
		)

	def convert(self, in_path, out_path, display, out_format=None):
		""" Converts an audio file into given output format.
		Required arguments:
			in_path -- Path to input file.
			out_path -- Path to output file.
			display -- String representing transfer.
		Optional arguments:
			out_format -- Output format. Defaults to Opus.
		Returns:
			display -- Pass straight through for multiprocessing callback.
		Side effects:
			Creates a new file with formatted audio.
		"""
		if not out_format:
			out_format = self.out_format
		in_file = audiotools.open(in_path)
		if self.quality:
			in_file.convert(out_path, out_format, compression=self.quality)
		else:
			in_file.convert(out_path, out_format)
		metadata = in_file.get_metadata()
		audiotools.open(out_path).set_metadata(metadata)
		return display

	def mkdirs(self):
		""" Makes representative directories for all directories in
		self.archive_path into self.portable_path.
		Arguments: None
		Returns: None
		Side effects:
			Creates a new directory for every directory not found in portable.
		"""
		for a_path in glob.iglob(self.archive_path + '/**/', recursive=True):
			out_path = self.portable_path + a_path[len(self.archive_path):]
			if out_path[:-1] not in self.portable:
				try:
					os.mkdir(out_path)
				except FileExistsError:
					pass

	def files(self):
		""" Copies all image files self.archive_path to self.portable_path and
		takes not of all audio needing conversion . Uses single loop for
		efficiency.
		Arguments: None
		Returns: None
		Side effects:
			Creates new image file for every image.
			Fills self.matches with strings for audio files needing conversion.
		"""
		for a_path in glob.iglob(self.archive_path + '/**', recursive=True):
			music = self.regex_music.match(a_path)
			if music:
				out_path = self.portable_path + music.group(2) + self.out_ext
				if out_path not in self.portable:
					self.matches.append((
						music.group(0), out_path, ''.join(music.group(2, 3))[1:]
					))
				continue
			image = self.regex_image.match(a_path)
			if image:
				out_path = self.portable_path + ''.join(image.group(2,3))
				if out_path not in self.portable:
					shutil.copyfile(a_path, out_path)
		self.total = len(self.matches)

	def run(self):
		""" Runs entire conversion process:
		1. Mimic directory structure.
		2. Transfer images.
		3. Convert music.
		Side effects:
			Creates a new directory for every directory not found in portable.
			Creates new image file for every image.
			Fills self.matches with strings for audio files needing conversion.
			Prints message to screen when completed.
		"""
		self.mkdirs()
		self.files()
		if self.total != 0:
			super().run(self.convert, self.matches)
		print(str(self.total) + ' files converted. Your library is up to date.')



if __name__ == '__main__':
	archive_path = ''
	portable_path = ''

	converter = MusicConverter(archive_path, portable_path, 'OpusAudio')
	converter.run()
