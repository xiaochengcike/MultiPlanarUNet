from glob import glob
import sys
import os
import numpy as np
import random
from MultiPlanarUNet.utils import create_folders
import argparse


def get_parser():
    parser = argparse.ArgumentParser(description="Prepare a data folder for a"
                                                 "CV experiment setup.")
    parser.add_argument("--data_dir", type=str,
                        help="Path to data directory")
    parser.add_argument("--CV", type=int, default=5,
                        help="Number of splits (default=5)")
    parser.add_argument("--out_dir", type=str, default="views",
                        help="Directory to store CV subfolders "
                             "(default=views")
    parser.add_argument("--im_sub_dir", type=str, default="images",
                        help="Subfolder under 'data_dir' in which image are "
                             "stored (default=images)")
    parser.add_argument("--lab_sub_dir", type=str, default="labels",
                        help="Subfolder under 'data_dir' in which labels are "
                             "stored (default=labels)")
    parser.add_argument("--aug_sub_dir", type=str, default="",
                        help="Optional subfolder under 'data_dir' in which "
                             "augmented files are stored. OBS: Assumes images "
                             "in sub-dir 'images' and labels in subdir 'labels"
                             "'. OBS: Augmented images must have identical "
                             "file name to the real image counterpart "
                             "(leading changes in augmented file name are "
                             "accepted).")
    parser.add_argument("--copy", action="store_true",
                        help="Copy files to CV-subfolders instead of "
                             "symlinking (not recommended)")
    parser.add_argument("--file_list", action="store_true",
                        help="Create text files with paths pointing to the "
                             "images at the image and labels subdirs under "
                             "each split instead of symlink/copying. This is"
                             " usefull on systems were symlink is not "
                             "supported, but the dataset size is too large to"
                             " store in copies. NOTE: Only one of --copy and "
                             "--file_list flags must be set.")
    parser.add_argument("--file_regex", type=str, default="*.nii*",
                        help="Regex used to select files from the image "
                             "and labels subdirs. (default='*.nii*')")
    parser.add_argument("--validation_fraction", type=float, default=0.20,
                        help="Fraction of OVERALL data size used for "
                             "validation in each split. In a 5-CV setting with "
                             "N=100 and val_frac=0.20, each split will have "
                             "N_train=60, N_val=20 and N_test=20 images")
    parser.add_argument("--test_fraction", type=float, default=0.20,
                        help="Fraction of data size used for test if CV=1.")
    return parser


def assert_dir_structure(data_dir, im_dir, lab_dir, out_dir):
    for _dir in (data_dir, im_dir, lab_dir):
        if not os.path.exists(_dir):
            raise OSError("Invalid data directory '%s'. Does not exist." % data_dir)
    if os.path.exists(out_dir):
        raise OSError("Output directory at '%s' already exists." % out_dir)


def create_view_folders(out_dir, n_splits):
    if not os.path.exists(out_dir):
        print("Creating directory at %s" % out_dir)
        os.makedirs(out_dir)

    if n_splits > 1:
        for i in range(n_splits):
            split_dir = os.path.join(out_dir, "split_%i" % i)
            print("Creating directory at %s" % split_dir)
            os.mkdir(split_dir)


def add_images(images, im_folder_path, label_folder_path, im_dir, lab_dir,
               link_func=os.symlink):
    for image in images:
        # Get file name
        file_name = os.path.split(image)[-1]

        # Get label path (OBS: filenames must match!)
        label = image.replace(im_dir, lab_dir)

        if not os.path.exists(label):
            raise OSError("No label file found at '%s'. OBS: image and "
                          "label files must have exactly the same name. "
                          "Images should be located at '%s' and labels at"
                          " '%s'" % (label, im_folder_path, label_folder_path))

        # Get relative paths
        rel_image = os.path.relpath(image, im_folder_path)
        rel_label = os.path.relpath(label, label_folder_path)

        # Symlink or copy
        link_func(rel_image, im_folder_path + "/%s" % file_name)
        link_func(rel_label, label_folder_path + "/%s" % file_name)


def _add_to_file_list_fallback(rel_image_path, image_path,
                               fname="LIST_OF_FILES.txt"):

    """
    On some system synlinks are not supported, if --files_list flag is set,
    uses this function to add each absolute file path to a list at the final
    subfolder that is supposed to store images and label links or actual files

    At run-time, these files must be loaded by reading in the path from these
    files instead.
    """
    # Get folder where list of files should be stored
    folder = os.path.split(image_path)[0]

    # Get absolute path to image
    # We change dir to get the correct abs path from the relative
    os.chdir(folder)
    abs_file_path = os.path.abspath(rel_image_path)

    # Get path to the list of files
    list_file_path = os.path.join(folder, fname)

    with open(list_file_path, "a") as out_f:
        out_f.write(abs_file_path + "\n")


def entry_func(args=None):

    # Get parser
    parser = vars(get_parser().parse_args(args))

    # Get arguments
    data_dir = os.path.abspath(parser["data_dir"])
    n_splits = int(parser["CV"])
    if n_splits > 1:
        out_dir = os.path.join(data_dir, parser["out_dir"], "%i_CV" % n_splits)
    else:
        out_dir = os.path.join(data_dir, parser["out_dir"], "fixed_split")
    im_dir = os.path.join(data_dir, parser["im_sub_dir"])
    lab_dir = os.path.join(data_dir, parser["lab_sub_dir"])
    if parser["aug_sub_dir"]:
        aug_dir = os.path.join(data_dir, parser["aug_sub_dir"])
    else:
        aug_dir = None
    copy = parser["copy"]
    file_list = parser["file_list"]
    regex = parser["file_regex"]
    val_frac = parser["validation_fraction"]
    test_frac = parser["test_fraction"]

    if n_splits == 1 and not test_frac:
        raise ValueError("Must specify --test_fraction with --CV=1.")
    if copy and file_list:
        raise ValueError("Only one of --copy and --file_list "
                         "flags must be set.")

    # Assert suitable folders
    assert_dir_structure(data_dir, im_dir, lab_dir, out_dir)

    # Create sub-folders
    create_view_folders(out_dir, n_splits)

    # Get images
    images = glob(os.path.join(im_dir, regex))

    if aug_dir:
        aug_im_dir = os.path.join(aug_dir, parser["im_sub_dir"])
        aug_lab_dir = os.path.join(aug_dir, parser["lab_sub_dir"])
        aug_images = glob(os.path.join(aug_im_dir, regex))
        aug_labels = glob(os.path.join(aug_lab_dir, regex))
        assert(len(aug_images) == len(aug_labels))

    # Get validation size
    N_total = len(images)
    if n_splits > 1:
        N_test = N_total // n_splits
    else:
        N_test = int(N_total * test_frac)
    N_val = int(N_total * val_frac)
    if N_val + N_test >= N_total:
        raise ValueError("Too large validation_fraction - "
                         "No training samples left!")
    N_train = N_total - N_test - N_val
    print("-----")
    print("Total images:".ljust(40), N_total)
    print("Train images pr. split:".ljust(40), N_train)
    print("Validation images pr. split:".ljust(40), N_val)
    print("Test images pr. split:".ljust(40), N_test)

    # Shuffle and split the images into CV parts
    random.shuffle(images)
    splits = np.array_split(images, n_splits)

    # Symlink / copy files
    for i, split in enumerate(splits):
        print("  Split %i/%i" % (i+1, n_splits), end="\r", flush=True)

        # Set root path to split folder
        if n_splits > 1:
            split_path = os.path.join(out_dir, "split_%i" % i)
        else:
            split_path = out_dir
            # Here we kind of hacky force the following code to work with CV=1
            # Define a test set and overwrite the current split (which stores
            # add the data, as splits was never split with n_splits=1
            split = splits[0][:N_test]

            # Overwrite the splits variable to a length 2 array with the
            # remaining data which will be used as val+train. The loop still
            # refers to the old split and thus will only execute once
            splits = [split, splits[0][N_test:]]

        # Define train, val and test sub-dirs
        train_path = os.path.join(split_path, "train")
        train_im_path = os.path.join(train_path, parser["im_sub_dir"])
        train_label_path = os.path.join(train_path, parser["lab_sub_dir"])
        val_path = os.path.join(split_path, "val")
        val_im_path = os.path.join(val_path, parser["im_sub_dir"])
        val_label_path = os.path.join(val_path, parser["lab_sub_dir"])
        test_path = os.path.join(split_path, "test")
        test_im_path = os.path.join(test_path, parser["im_sub_dir"])
        test_label_path = os.path.join(test_path, parser["lab_sub_dir"])
        if aug_dir:
            aug_path = os.path.join(split_path, "aug")
            aug_im_path = os.path.join(aug_path, parser["im_sub_dir"])
            aug_label_path = os.path.join(aug_path, parser["lab_sub_dir"])
        else:
            aug_path, aug_im_path, aug_label_path = None, None, None

        # Create folders if not existing
        create_folders([train_path, val_path, train_im_path, train_label_path,
                        val_im_path, val_label_path, test_path, test_im_path,
                        test_label_path, aug_path, aug_im_path, aug_label_path])

        # Copy or symlink?
        if copy:
            from shutil import copyfile
            move_func = copyfile
        elif file_list:
            move_func = _add_to_file_list_fallback
        else:
            move_func = os.symlink

        # Add test data to test folder
        add_images(split, test_im_path, test_label_path, im_dir, lab_dir, move_func)

        # Join remaining splits into train+val
        remaining = [x for ind, x in enumerate(splits) if ind != i]
        remaining = [item for sublist in remaining for item in sublist]

        # Extract validation data from the remaining
        random.shuffle(remaining)
        validation = remaining[:N_val]
        training = remaining[N_val:]

        # Add
        add_images(validation, val_im_path, val_label_path, im_dir, lab_dir, move_func)
        add_images(training, train_im_path, train_label_path, im_dir, lab_dir, move_func)

        # Add augmented images to training dir?
        if aug_dir:
            # Get list of train file names
            train_fnames = [os.path.split(f)[-1] for f in training]
            augmented = []
            for aug_im in aug_images:
                aug_im_fname = os.path.split(aug_im)[-1]
                if any([t_fn in aug_im_fname for t_fn in train_fnames]):
                    augmented.append(aug_im)

            # Add the images
            add_images(augmented, aug_im_path, aug_label_path,
                       aug_im_dir, aug_lab_dir, move_func)


if __name__ == "__main__":
    entry_func()
