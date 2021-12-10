<img align="right" src="https://github.com/FZJ-INM1-BDA/siibra-python/raw/main/images/siibra-python.jpeg" width="200">

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![PyPI version](https://badge.fury.io/py/siibra.svg)](https://pypi.org/project/siibra/)
[![Python versions](https://img.shields.io/pypi/pyversions/siibra.svg)](https://pypi.python.org/pypi/siibra)
[![Documentation Status](https://readthedocs.org/projects/siibra-python/badge/?version=latest)](https://siibra-python.readthedocs.io/en/latest/?badge=latest)

# siibra - Python interface for interacting with brain atlases 

Copyright 2020-2021, Forschungszentrum Jülich GmbH 

*Authors: Big Data Analytics Group, Institute of Neuroscience and Medicine (INM-1), Forschungszentrum Jülich GmbH*


<!--- Please keep this at line 15, or adjust the line skip in docs/readme.rst accordingly -->

`siibra` is a Python client for working with "multilevel" brain atlas frameworks, and aims to facilitate the programmatic and reproducible incorporation of brain region definitions and multidimensional brain region features into reproducible neuroscience workflows.
**Note that `siibra-python` is still in development.** While care is taken to make everything work reliably, the API of the library is not yet stable, and the software is not yet fully tested. 
`siibra` provides structured acccess to parcellation schemes in different brain reference spaces, including volumetric reference templates at both macroscopic and microscopic resolutions as well as surface representations. It supports both discretely labelled and continuous (probabilistic) parcellation maps, which can be used to assign brain regions to spatial locations and image signals, to retrieve region-specific neuroscience datasets from multiple online repositories, and to sample information from high-resolution image data. Among the datasets anchored to brain regions are many different modalities from in-vivo and post mortem studies, including regional information about cell and transmitter receptor densties, structural and functional connectivity, gene expressions, and more.

`siibra` is mainly developed by the [Human Brain Project](https://humanbrainproject.eu) for accessing the [EBRAINS human brain atlas](https://ebrains.eu/service/human-brain-atlas). 
It stores much of its contents in the [EBRAINS Knowledge Graph](https://kg.ebrains.eu), and is designed to support the [OpenMINDS metadata standards](https://github.com/HumanBrainProject/openMINDS_SANDS).
Its functionalities include common actions known from the interactive viewer `siibra explorer` [hosted on EBRAINS](https://atlases.ebrains.eu/viewer). 
In fact, the viewer is a good resource for exploring `siibra`'s core functionalities interactively: 
Selecting different parcellations, browsing and searching brain region hierarchies, downloading maps, identifying brain regions, and accessing multimodal features and connectivity information associated with brain regions. Feature queries in `siibra` are parameterized by data modality and anatomical location, while the latter could be a brain region, brain parcellation, or location in reference space.
Beyond the functionality of `siibra-explorer`, the Python library also supports a range of data analysis features suitable for typical neuroscience workflows.

`siibra` hides much of the complexity that would be required to collect and interact with the individual paracellations,templates andd data repositories.
By encapsulating many aspects of interacting with different maps and reference templates spaces, it also minimizes common errors like misinterpretation of coordinates from different reference spaces, mixing up label indices of brain regions, or utilisation of inconsistent versions of parcellation maps. 
It aims to provide a safe way of using maps defined across multiple spatial scales for reproducible analysis. 

# Installation

`siibra` is available on pypi. To install the latest released version, simply run `pip install siibra`. In order to work with the latest version from github, use `pip install git+https://github.com/FZJ-INM1-BDA/siibra-python.git@main`. 

# Access to EBRAINS

`siibra` retrieves much of its data from the [EBRAINS Knowledge Graph](https://kg.ebrains.eu), which requires authentication. 
Therefore you have to provide an EBRAINS authentication token for using all features provided by `siibra`.
Please make sure that you have a valid EBRAINS user account by [registering to EBRAINS](https://ebrains.eu/register/). 
Then follow the instructions for [obtaining EBRAINS API auth tokens](https://kg.ebrains.eu/develop.html).
As a last step, you need to fetch a recent token from the [authorization endpoint](https://nexus-iam.humanbrainproject.org/v0/oauth2/authorize), and make it known to `siibra` using either `siibra.set_ebrains_token()` or by storing it in the environment variable `HBP_AUTH_TOKEN`.  Note that as of now, you need to get a new token approximately every day to perform EBRAINS data queries. However, `siibra` implements a local cache on your harddisk, so once retrieved, your data will become usable and accessible without refreshing the token.

# Documentation & Help

`siibra-python`'s documentation is hosted at https://siibra-python.readthedocs.io. It includes a catalogue of well documented code examples that walk you through the different concepts and functionalities. As a new user, it is recommended to go through these examples - they are easy and will quickly provide you with the right code snippets that get you started. Furthermore, a set of jupyter notebooks demonstrating concrete example usecases are maintained in the [siibra-tutorials](https://github.com/FZJ-INM1-BDA/siibra-tutorials) repository. 

If you run into issues, please open a ticket on [EBRAINS support](https://ebrains.eu/support/) or directly file bugs and feature requests on [github](https://github.com/FZJ-INM1-BDA/siibra-python/issues).
Please keep in mind that `siibra-python` is still in development. While care is taken to make everything work reliably, the API of the library is not yet stable, and the software is not yet fully tested. 

# How to contribute

If you want to contribute to `siibra`, feel free to fork it and open a pull request with your changes. You are also welcome to contribute to discussion in the issue tracker and of course to report issues you are facing yourself.
If you find the software useful, please reference this repository URL in publications and derived work.
You can also star the project to show us that you are using it.

# Acknowledgements

This software code is funded from the European Union’s Horizon 2020 Framework Programme for Research and Innovation under the Specific Grant Agreement No.
945539 (Human Brain Project SGA3).
