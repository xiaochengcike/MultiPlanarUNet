"""
Mathias Perslev
MSc Bioinformatics

University of Copenhagen
November 2017
"""

import glob
import os
import numpy as np

from .image_pair import ImagePair
from MultiPlanarUNet.logging import ScreenLogger


class ImagePairLoader(object):
    """
    ImagePair data loader object
    Represents a collection of ImagePairs
    """
    def __init__(self, base_dir="./", img_subdir="images",
                 label_subdir="labels", logger=None,
                 sample_weight=1.0, predict_mode=False, single_file_mode=False,
                 no_log=False, **kwargs):
        """
        Initializes the ImagePairLoader object from all .nii files in a folder
        or pair of folders if labels are also specified.

        If single_file_mode=False, the following actions are taken immediately
        on initialization:
            - All .nii/.nii.gz image files are found in base_dir/img_subdir
            - Unless predict_mode=True, finds all .nii/.nii.gz label files in
              base_dir/label_subdir
            - ImagePair objects are established for all images/image-label
              pairs. Not that since ImagePairs do not eagerly load data,
              the ImagePairLoader also does not immediately load data into mem

        If single_file_mode=True, the class is initialized but no images are
        loaded. Images can be manually added through the add_image, add_images
        and add_augmented_images methods.

        Args:
            base_dir:           A path to a directory storing the 'img_subdir'
                                and 'label_subdir' sub-folders
            img_subdir:         Name of sub-folder storing .nii images files
            label_subdir:       Name of sub-folder storing .nii labels files
            logger:             MultiPlanarUNet logger object
            sample_weight:      A float giving a global sample weight assigned
                                to all images loaded by the ImagePairLoader
            predict_mode:       Boolean whether labels exist for the images.
                                If True, the labels are assumed stored in the
                                label_subdir with names identical to the images
            single_file_mode:   Boolean, if True do not load any images at init
                                This may be useful for manually assigning
                                individual image files to the object.
            no_log:             Boolean, whether to not log to screen/file
            **kwargs:           Other keywords arguments
        """
        self.logger = logger if logger is not None else ScreenLogger()

        # Set absolute paths to main folder, image folder and label folder
        self.data_dir = os.path.abspath(base_dir)
        self.images_path = os.path.join(self.data_dir, img_subdir)

        # Labels included?
        self.predict_mode = predict_mode
        if not predict_mode:
            self.labels_path = os.path.join(self.data_dir, label_subdir)
        else:
            self.labels_path = None

        # Load images unless single_file_mode is specified
        if not single_file_mode:
            # Get paths to all images
            self.image_paths = self.get_image_paths()

            if not predict_mode:
                # Get paths to labels if included
                self.label_paths = self.get_label_paths(img_subdir,
                                                        label_subdir)
            else:
                self.label_paths = None

            # Load all nii objects
            self.images = self.get_image_objects(sample_weight)
        else:
            self.images = []

        if not single_file_mode and not self.image_paths:
            raise OSError("No image files found at %s." % self.images_path)
        if not single_file_mode and not predict_mode and not self.label_paths:
            raise OSError("No label files found at %s." % self.labels_path)

        if not no_log:
            self._log()

        # Stores ImageQueue object if max_load specified via self.set_queue
        self.queue = False

    def set_queue(self, max_load):
        """
        Add a ImageQueue object to this ImagePairLoader. Images fetched through
        self.get_random will be taken from the queue object

        Args:
            max_load: Int, maximum number of (loaded) ImagePairs to store in
                      the queue at once
        """
        # Set dictionary pointing to images by ID
        if isinstance(max_load, int) and max_load < len(self):
            from MultiPlanarUNet.image.image_queue import ImageQueue

            self.logger("OBS: Using max load %i" % max_load)
            self.queue = ImageQueue(max_load, self)

    def __str__(self):
        return "<ImagePairLoader object : %i images @ %s>" % (len(self), self.data_dir)

    def __repr__(self):
        return self.__str__()

    def __getitem__(self, item):
        return self.images[item]

    def __iter__(self):
        for im in self.images:
            yield im

    def __len__(self):
        return len(self.images)

    def _log(self):
        self.logger(str(self))
        self.logger("--- Image subdir: %s\n--- Label subdir: %s" % (self.images_path,
                                                                    self.labels_path))

    @property
    def id_to_image(self):
        """
        Returns:
            A dictionary of image IDs pointing to image objects
        """
        return {image.id: image for image in self}

    def get_by_id(self, image_id):
        """
        Get a specific ImagePair by its string identifier

        Args:
            image_id: String ID of an ImagePair

        Returns:
            An ImagePair
        """
        return self.id_to_image[image_id]

    def get_random(self, N=1, unique=False):
        """
        Return N random images, with or without re-sampling

        Args:
            N:      Int, number of randomly sampled images to return
            unique: Bool, whether the sampled images should be all unique

        Returns:
            A list of ImagePair objects
        """
        returned = []
        while len(returned) < N:
            if self.queue:
                with self.queue.get() as image:
                    if unique and image in returned:
                        continue
                    else:
                        returned.append(image)
                        yield image
            else:
                image = self.images[np.random.randint(len(self))]
                if unique and image in returned:
                    continue
                else:
                    returned.append(image)
                    yield image

    def _get_paths_from_list_file(self, base_path, fname="LIST_OF_FILES.txt"):
        """
        Loads a set of paths pointing to .nii files in 'base_path'.
        This method is used in the rare cases that images are not directly
        stored in self.images_path or self.labels_path but those paths stores
        a file named 'fname' storing 1 absolute path per line pointing to the
        images to load.

        Args:
            base_path: A path to a folder
            fname:     The filename of the file at 'base_path' that stores the
                       paths to return

        Returns:
            A list of path strings
        """
        # Check if a file listing paths exists instead of actual files at the
        # image sub folder path
        list_file_path = os.path.join(base_path, fname)
        images = []
        if os.path.exists(list_file_path):
            with open(list_file_path, "r") as in_f:
                for path in in_f:
                    path = path.strip()
                    if not path:
                        continue
                    images.append(path)
        else:
            raise OSError("File '%s' does not exist. Did you specify "
                          "the correct img_subdir?" % list_file_path)
        return images

    def get_image_paths(self):
        """
        Return a list of paths to all image files in the self.images_path folder

        Returns:
            A list of path strings
        """
        images = sorted(glob.glob(self.images_path + "/*.nii*"))
        if not images:
            # Try to load from a file listing paths at the location
            # This is sometimes a format created by the cv_split.py script
            images = self._get_paths_from_list_file(self.images_path)
        return images

    def get_label_paths(self, img_subdir, label_subdir):
        """
        Return a list of paths to all label files in the self.labels_path folder
        The label paths are assumed to be identical to the image paths with the
        image subdir name replaced by the label subdir name.

        Args:
            img_subdir:   String, name of the image sub-folder
            label_subdir: String, name of the label sub-folder

        Returns:
            A list of path strings
        """
        if any([img_subdir not in p for p in self.image_paths]):
            raise ValueError("Mismatch between image paths and specified "
                             "img_subdir. The subdir was not found in one or"
                             " more image paths - Do the paths in "
                             "LIST_OF_FILES.txt point to a subdir of name "
                             "'%s'?" % img_subdir)
        return [p.replace("/%s/" % img_subdir, "/%s/" % label_subdir) for p in self.image_paths]

    def get_image_objects(self, sample_weight):
        """
        Initialize all ImagePair objects from paths at self.image_paths and
        self.label_paths (if labels exist). Note that data is not loaded
        eagerly.

        Args:
            sample_weight: A float giving the weight to assign to the ImagePair

        Returns:
            A list of initialized ImagePairs
        """
        image_objects = []
        if self.predict_mode:
            for img_path in self.image_paths:
                image = ImagePair(img_path, sample_weight=sample_weight,
                                  logger=self.logger)
                image_objects.append(image)
        else:
            for img_path, label_path in zip(self.image_paths, self.label_paths):
                image = ImagePair(img_path, label_path,
                                  sample_weight=sample_weight,
                                  logger=self.logger)
                image_objects.append(image)

        return image_objects

    def add_image(self, image_pair):
        """
        Add a single ImagePair object to the ImagePairLoader

        Args:
            image_pair: An ImagePair
        """
        self.images.append(image_pair)

    def add_images(self, image_pair_loader):
        """
        Add a set of ImagePair objects to the ImagePairLoader. Input can be
        either a different ImagePairLoader object or a list of ImagePairs.

        Args:
            image_pair_loader: ImagePairLoader or list of ImagePairs

        Returns:
            self
        """
        try:
            self.images += image_pair_loader.images
        except AttributeError:
            # Passed as list?
            self.images += list(image_pair_loader)
        return self

    def add_augmented_images(self, aug_loader):
        """
        Alias for add_images, see docstring for add_images
        """
        return self.add_images(aug_loader)

    def get_class_weights(self, as_array=True, return_counts=False, unload=False):
        """
        Passes self to the utility function get_class_weights, which computes
        a class weight for all classes across the stored ImagePairs.
        Note that labels must exist.

        Args:
            as_array:       Boolean, return an array of weights instead of dictionary
                            pointing from class ints to weights
            return_counts:  Boolean, also return the class counts as an array
                            or dict (per as_array)
            unload:         Boolean, unload each image after counting (useful
                            with queueing as otherwise all images will be kept
                            in memory)

        Returns:
            A dictionary mapping class integers to weights or array of weights
            for each class if as_array=True
            If return_counts = True, also return a list/dict of class counts
        """
        if self.predict_mode:
            raise ValueError("Cannot compute class weights without labels "
                             "(predict_mode=True) set for this ImagePairLoader")
        from MultiPlanarUNet.utils import get_class_weights
        return get_class_weights(self, as_array, return_counts, unload)

    def get_maximum_real_dim(self):
        """
        Returns the longest distance in mm covered by any axis across images
        of this ImagePairLoader.

        Returns:
            A float
        """
        from MultiPlanarUNet.interpolation.sample_grid import get_maximum_real_dim
        return np.max([get_maximum_real_dim(f.image_obj) for f in self])

    def set_normalizer(self, scaler, **kwargs):
        """
        Set and fit a scaler on all stored ImagePair objects.
        The scaler should be a sklearn preprocessing scaler, which will be
        wrapped by the MultiPlanarUNet MultiChannelScaler object which will fit
        (and apply when called) the scaler to each channel separately.

        Args:
            scaler:   String name of sklearn scaler class
            **kwargs: Other arguments, not used
        """
        for image in self:
            image.set_scaler(scaler)
            image.log_image()

    def prepare_for_iso_live_views(self, bg_class, bg_value, scaler, **kwargs):
        """
        Loads all images and prepares them for iso-live view interpolation
        training by performing the following operations on each:
            1) Loads the image and labels if not already loaded (transparent)
            2) Define proper background value
            3) Setting multi-channel scaler
            4) Setting interpolator object

        Args:
            bg_class: See ImagePair.prepare_for_iso_live_views
            bg_value: See ImagePair.prepare_for_iso_live_views
            scaler:   See ImagePair.prepare_for_iso_live_views
            **kwargs: Additional keyword arguments
        """
        # Log some things...
        self.logger("Preparing isotrophic live-interpolation...")
        self.logger("Performing '%s' scaling\n" % scaler)

        # Run over volumes: scale, set interpolator, check for affine
        for image in self.id_to_image.values():
            image.prepare_for_iso_live(bg_value, bg_class, scaler)

            # Log basic stats for the image
            image.log_image()

    def get_sequencer(self, intrp_style, is_validation=False, **kwargs):
        """
        Prepares the images of the ImagePairLoader for a MultiPlanar.sequence
        object. These generator-like objects pull data from ImagePairs during
        training as needed. The sequences are specific to the model type (for
        instance 2D and 3D models have separate sequence classes) and may
        differ in the interpolation schema as well (voxel vs. iso scanner space
        coordinates for instance).

        This method calls various preparation methods on all ImagePair objects.
        These may perform standardization, setup interpolators etc. The preped
        ImagePairs are then passed to the appropriate sequencer.

        Note: If the ImagePairLoader is queued with a ImageQueue object, the
        prep functions are not called immediately but by the queue object
        when needed. See MultiPlanarUNet.image.image_queue

        Args:
            intrp_style:   String identifier for the interpolation mode
                           Must be "iso_live", "iso_live_3d", "patches_3d" or
                           "sliding_patches_3d"
            is_validation: Boolean, is this a validation sequence? (otherwise
                           training)
            **kwargs:      Additional arguments passed to the prep function

        Raises:
            ValueError if intrp_style is not valid
        """
        aug_list = []
        if not is_validation:
            # On the fly augmentation?
            list_of_aug_dicts = kwargs.get("augmenters")
            if list_of_aug_dicts:
                self.logger("Using on-the-fly augmenters:")
                from MultiPlanarUNet.augmentation import augmenters
                for aug in list_of_aug_dicts:
                    aug_cls = augmenters.__dict__[aug["cls_name"]](**aug["kwargs"])
                    aug_list.append(aug_cls)
                    self.logger(aug_cls)

        if intrp_style.lower() == "iso_live":
            # Isotrophic 2D plane sampling
            from MultiPlanarUNet.sequences import IsotrophicLiveViewSequence2D

            if not self.queue:
                # Prepare and return Iso live view sequence object
                self.prepare_for_iso_live_views(**kwargs)
            else:
                in_kw = {key: kwargs[key] for key in ("bg_value", "bg_class", "scaler")}
                self.queue.set_entry_func("prepare_for_iso_live", in_kw)
                self.queue.set_exit_func("unload")

                # Start queue
                self.queue.start(n_threads=3)
                self.queue.await_full()

            return IsotrophicLiveViewSequence2D(self,
                                                is_validation=is_validation,
                                                use_queue=bool(self.queue),
                                                list_of_augmenters=aug_list,
                                                logger=self.logger,
                                                **kwargs)

        elif intrp_style.lower() == "iso_live_3d":
            # Isotrophic 3D box sampling
            from MultiPlanarUNet.sequences import IsotrophicLiveViewSequence3D

            if not self.queue:
                # Prepare and return Iso live view sequence object
                self.prepare_for_iso_live_views(**kwargs)
            else:
                in_kw = {key: kwargs[key] for key in ("bg_value", "bg_class", "scaler")}
                self.queue.set_entry_func("prepare_for_iso_live", in_kw)
                self.queue.set_exit_func("unload")

                # Start queue
                self.queue.start(n_threads=3)
                self.queue.await_full()

            return IsotrophicLiveViewSequence3D(self,
                                                is_validation=is_validation,
                                                use_queue=bool(self.queue),
                                                list_of_augmenters=aug_list,
                                                logger=self.logger,
                                                **kwargs)

        elif intrp_style.lower() == "patches_3d":
            # Random selection of boxes
            from MultiPlanarUNet.sequences import PatchSequence3D

            if not self.queue:
                self.set_normalizer(**kwargs)
            else:
                in_kw = {key: kwargs[key] for key in ("bg_value", "scaler")}
                self.queue.set_entry_func("set_scaler", in_kw)
                self.queue.set_exit_func("unload")

                # Start queue
                self.queue.start(n_threads=3)
                self.queue.await_full()

            return PatchSequence3D(self,
                                   is_validation=is_validation,
                                   list_of_augmenters=aug_list, **kwargs)

        elif intrp_style.lower() == "sliding_patches_3d":
            # Sliding window selection of boxes
            from MultiPlanarUNet.sequences import SlidingPatchSequence3D

            if not self.queue:
                self.set_normalizer(**kwargs)
            else:
                in_kw = {key: kwargs[key] for key in ("bg_value", "scaler")}
                self.queue.set_entry_func("set_scaler", in_kw)
                self.queue.set_exit_func("unload")

                # Start queue
                self.queue.start(n_threads=3)
                self.queue.await_full()
            return SlidingPatchSequence3D(self,
                                          is_validation=is_validation,
                                          list_of_augmenters=aug_list,
                                          **kwargs)
        else:
            raise ValueError("Invalid interpolator schema '%s' specified"
                             % intrp_style)
