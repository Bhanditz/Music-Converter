import re
import os
import sys
import glob
import time
import shutil
import logging
import audiotools
import multiprocessing
from copy import deepcopy
from collections import defaultdict

class FailedJob(Exception):
	def __init__(self, original_exception, identifier):
		self.original_exception = original_exception
		self.id = identifier

class JobTracker:
	""" Object used to manage and document progress of multiprocessing pool. """
	def __init__(self, log_prefix='jt_', total=0):
		self.prog, self.fails = 0, []
		self.total = total
		self.procs = multiprocessing.cpu_count()
		self.lines = self.procs + 5
		self.done = 'Waiting for first file to complete . . .'
		self.log_init(log_prefix)
		# Create manager for objects start_job() modifies.
		manager = multiprocessing.Manager()
		self.active = manager.list()
		self.log_queue = manager.list()
		self.queue = manager.list()
		self.lock = manager.RLock()
		self.log_lock = manager.RLock()

	def log_init(self, prefix):
		try:
			os.mkdir('log')
		except FileExistsError:
			pass
		val = 0
		def name(level, val):
			mid = '.' + str(val) if val else ''
			return 'log/' + prefix + level + mid + '.log'
		levels = ['debug', 'info', 'error']
		filenames = []
		for level in levels:
			while True:
				if os.path.exists(name(level, val)):
					val += 1
				else:
					break
		filenames = [name(level, val) for level in levels]
		self.debug_log, self.info_log, self.error_log = filenames


	def log_add(self, message, level='ERROR'):
		self.log_lock.acquire()
		self.log_queue.append((
			time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(time.time())),
			level,
			message
		))
		self.log_lock.release()

	def log_write(self):
		# Quickly copy and clear so it can be changed during write.
		self.log_lock.acquire()
		log_buffer = deepcopy(self.log_queue)
		del self.log_queue[:]
		self.log_lock.release()
		loglevels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']
		with open(self.debug_log, 'a') as d, \
		     open(self.info_log, 'a') as i,  \
		     open(self.error_log, 'a') as e:
			for msg in log_buffer:
				level = loglevels.index(msg[1])
				formsg = '{} - {}: {}\n'.format(*msg)
				d.write(formsg)
				if level < 4:
					i.write(formsg)
					if level < 2:
						e.write(formsg)

	def queue_job(self, new):
		""" Takes note that a job has started and refreshes the display.
		Required arguments:
			new -- String representation for newly started job.
		Returns: None
		Side effects:
			Adds new to list of active jobs.
			Sends new string to stdout.
		"""
		self.queue.append(new)
		self.log_add('Job queued: ' + new, 'DEBUG')
		#self.show_state()

	def start_job(self, new):
		""" Takes note that a job has started and refreshes the display.
		Required arguments:
			new -- String representation for newly started job.
		Returns: None
		Side effects:
			Locks any other start_job() functions while active
			Adds new to list of active jobs.
			Removes new from queue.
		"""
		self.lock.acquire()
		self.queue.remove(new)
		self.active.append(new)
		self.log_add('Job started: ' + new, 'INFO')
		# Without pause we have problems accumulating first jobs in the log.
		# Yes, even with the RLock().
		time.sleep(0.02)
		self.lock.release()

	def end_job(self, rm):
		""" Takes note that a job has completed successfully.
		Required arguments:
			rm -- String representation for completed job
		Returns: None
		Side effects:
			Increments progress counter by one.
			Removes rm from list of active jobs.
			Sets latest finished job --> self.done
		"""
		self.prog += 1
		self.active.remove(rm)
		self.done = rm
		self.log_add('Job completed: ' + rm, 'INFO')

	def job_failed(self, exception):
		if isinstance(exception, FailedJob):
			self.active.remove(exception.id)
			self.fails.append(exception.id)
			self.log_add('Job failed: ' + exception.id + ' - exception: '
			             + repr(exception.original_exception), 'ERROR')
		else:
			self.log_add(repr(exception), 'CRITICAL')

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
		print('\n' * (self.lines - 1))
		self.start = time.time()
		self.math_start = self.start
		results = []
		with multiprocessing.Pool() as pool:
			for item in args_list:
				self.queue_job(item[2])
				# apply() instead of starmap() to get immediate callbacks
				# This reduces the number of shared resources needed
				results.append(pool.apply_async(fun, item, callback=self.end_job,
					                            error_callback=self.job_failed))
				self.log_write()
			time.sleep(0.5)
			# Wait for results, print to screen periodically.
			for res in results:
				self.log_write()
				go = True
				while go:
					self.show_state()
					try:
						res.get(0.1)
						go = False
					except multiprocessing.context.TimeoutError:
						pass
					except FailedJob as e:
						go = False
		self.log_write()
		pool.join()

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
		# Active list
		active = deepcopy(self.active)
		n_left = len(self.queue) + len(active)
		n_active = len(active)
		a = [p[:min(width, len(p))] for p in active]
		pad = ['' for i in range(self.procs - n_active) if n_active < self.procs]
		title = ' Currently Converting '
		try:
			border = '═'*int((len(max(a, key=len)) - len(title))/2)
		except ValueError as e:
			border = '═'
		curr = border + title + border + '\n' + '\n'.join((a + pad)[::-1])
		# Status display
		spent = time.time() - self.start
		try:
			1 / (self.total - n_left)
			# Add len(a)/2 to assume that we are halfway done with active jobs
			time_left = ((self.total / (self.total - n_left + len(a)/2)) - 1)*spent
		except ZeroDivisionError:
			time_left = -1
		stats_list = [
			(' Latest conversion', self.done[:min(width - 21, len(self.done))]),
			('   Files remaining', '{} of {}'.format(n_left, self.total)),
			('        Time spent', '{:.0f} s'.format(spent)),
			('Est time remaining', '{:.0f} s'.format(time_left))
		]
		stats = '\n'.join([' │ '.join(stat) for stat in stats_list])
		# Progress bar
		fill = int(done * width)
		blank = width - fill
		if fill > blank:
			fill -= 6
		else:
			blank -= 6
		bar = '{}{} {} %'.format('█' * fill, '░' * blank, int(done * 100))
		# Blank the output
		blank = '\n'.join([' '*width for i in range(self.lines+1)])
		sys.stdout.write('\033[F'*self.lines + blank)
		# Redraw new output
		sys.stdout.write('\033[F'*self.lines + curr +'\n'+ bar +'\n'+ stats)
		sys.stdout.flush()



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
	# These lists are not comprehensive, add more.
	music_ext = [
		'wav', 'aiff', 'wma', 'alac', 'spx', 'wv', 'ogg' #, 'ape'
		'mp2', 'opus', 'shn', 'flac', 'mp3', 'au', 'm4a'
	]
	image_ext = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tif']

	def __init__(self, archive_path, portable_path, out_format, quality=None):
		super().__init__(log_prefix='mc_')
		self.archive_path = archive_path
		self.portable_path = portable_path
		self.matches = []
		self.portable = set(glob.glob(glob.escape(portable_path) + '/**', recursive=True))
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
			'({})(.*\.)({})$'.format(re.escape(self.archive_path), '|'.join(t))
		)

	def worker(self, *args):
		try:
			return self.convert(*args)
		except Exception as e:
			raise FailedJob(e, args[2])

	def convert(self, in_path, out_path, identifier, out_format=None):
		""" Converts an audio file into given output format.
		Required arguments:
			in_path -- Path to input file.
			out_path -- Path to output file.
			identifier -- String representing transfer.
		Optional arguments:
			out_format -- Output format. Defaults to Opus.
		Returns:
			identifier -- Pass straight through for multiprocessing callback.
		Side effects:
			Creates a new file with formatted audio.
		"""
		self.start_job(identifier)
		if not out_format:
			out_format = self.out_format
		in_file = audiotools.open(in_path)
		if self.quality:
			in_file.convert(out_path, out_format, compression=self.quality)
		else:
			in_file.convert(out_path, out_format)
		metadata = in_file.get_metadata()
		audiotools.open(out_path).set_metadata(metadata)
		return identifier

	def mkdirs(self):
		""" Makes representative directories for all directories in
		self.archive_path into self.portable_path.
		Arguments: None
		Returns: None
		Side effects:
			Creates a new directory for every directory not found in portable.
		"""
		for a_path in glob.iglob(glob.escape(self.archive_path) + '/**/', recursive=True):
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
		for a_path in glob.iglob(glob.escape(self.archive_path) + '/**', recursive=True):
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
		print('Scanning library . . .')
		self.mkdirs()
		self.files()
		if self.total != 0:
			super().run(self.worker, self.matches)
		fails = len(self.fails)
		print('\n\n' + str(self.total - fails) + ' files converted.')
		if fails > 0:
			print('\n{} files failed to convert! See error.log.'.format(fails))
		else:
			print('Library up to date.')


if __name__ == '__main__':
	archive_path = ''
	portable_path = ''

	converter = MusicConverter(archive_path, portable_path, 'OpusAudio')
	converter.run()
