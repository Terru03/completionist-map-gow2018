"""Build two-family test with paired resident textures over completion v6.

This is a coexistence candidate, not evidence that the renderer is fixed.
Do not expand it to the other families until Raven, Artefact and Wooden Chest
have been observed together, including after a cold restart.
"""
from pathlib import Path
import argparse

import collectible_family_art as art
import collectible_art_textures as textures

FAMILIES = ('artefact', 'wooden_chest')
OUTPUT = art.BUILD / 'resident-pairs-probe'


def inputs():
    result = textures.source_inputs(FAMILIES)
    result[Path(__file__).relative_to(art.ROOT).as_posix()] = textures.io.sha(Path(__file__))
    return result


def build(game=art.locations.GAME, output=OUTPUT):
    game, output = textures.io.safe(game), textures.io.safe(output)
    art.need(not output.is_relative_to(game) and not game.is_relative_to(output), 'output overlaps game')
    if not (output / 'baseline.json').exists():
        textures.freeze_baseline(game, output)
    textures.check_baseline(game, output)
    sources = inputs()
    work, compiled = textures.compile_textures(output, sources, FAMILIES)
    first, proof = textures.compose(output, work, compiled, isolate_render_resources=True)
    second, repeated = textures.compose(output, work, compiled, isolate_render_resources=True)
    art.need(first == second and proof == repeated, 'repeat render-probe composition differs')
    art.need(proof[art.MASTER]['families'] == {'artefact': 45, 'wooden_chest': 99},
             'two-family marker scope differs')
    art.need(inputs() == sources, 'source changed during build')
    textures.check_baseline(game, output)
    proof.update(two_compositions_equal=True, profile='paired-resident-private-mg-ps-two-family-v2',
                 live_acceptance='Raven, Artefact and Wooden Chest stay distinct after cold restart')
    result = art.freeze_package(first, proof, output, baseline_root=output, source_inputs=sources)
    print('RENDER_PROBE_BUILT types=2 markers=144 package=' + result['package_id'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=art.locations.GAME)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.game, args.output)
