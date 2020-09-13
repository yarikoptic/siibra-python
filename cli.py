#!/usr/bin/env python3

import click
import logging
import brainscapes.atlas as bsa
import brainscapes.preprocessing as proc
from brainscapes.ontologies import atlases, parcellations, spaces

@click.group()
def brainscapes():
    """ Command line interface to the brainscapes atlas services.
    """
    pass    

def complete_parcellations(ctx, args, incomplete):
    """ auto completion for parcellations """
    return dir(parcellations)

def complete_spaces(ctx, args, incomplete):
    """ auto completion for parcellations """
    return dir(spaces)

@brainscapes.command()
@click.argument('parcellation', 
        type=click.STRING, 
        autocompletion=complete_parcellations)
@click.argument('space', 
        type=click.STRING, 
        autocompletion=complete_spaces)
@click.option('--cache', default=None, type=click.Path(dir_okay=True),
        help="Local directory for caching downloaded files. If none, a temporary directory will be used.")
@click.pass_context
def regionprops(ctx,parcellation,space,cache):
    """
    Test command for extracting core properties of atlas regions as requested by TVB.
    """

    if not hasattr(parcellations,parcellation):
        logging.error("No such parcellation available: "+parcellation)
        exit(1)
    parcellation_obj = getattr(parcellations,parcellation)
    spaces_obj = getattr(spaces,space)

    # Extract properties of all atlas regions
    atlas = bsa.Atlas(cachedir=cache)
    atlas.select_parcellation_scheme(parcellation_obj)
    lbl_volumes = atlas.get_maps(spaces_obj)
    tpl_volume = atlas.get_template(spaces_obj)
    props = proc.regionprops(lbl_volumes,tpl_volume)

    # Generate commandline report
    for region in atlas.regions():
        label = int(region.labelIndex)
        if label not in props.keys():
            print("{n:40.40}  {na[0]:>12.12} {na[0]:>12.12} {na[0]:>12.12}  {na[0]:>10.10}  {na[0]:>10.10}".format(
                n=region.name, na=["N/A"]*5))
            continue
        for prop in props[label]:
            # FIXME this identifies left/right hemisphere labels for
            # Julich-Brain, but is not a general solution
            if prop.labelled_volume_description in region.name:
                print("{n:40.40}  {c[0]:12.1f} {c[1]:12.1f} {c[2]:12.1f}  {v:10.1f}  {s:10.1f}".format(
                    n=region.name, 
                    c=prop.centroid_mm,
                    v=prop.volume_mm,
                    s=prop.surface_mm
                    ))
