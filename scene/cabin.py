# The cabin: builds the scene from scratch and writes everything the site uses.
#   public/cabin-still.webp   1920x1080 Cycles render, the homepage's first paint
#   public/og.jpg             1200x630 share card
#   public/scene/cabin.glb    the live scene: baked cabin, laptop screen, window glass, Saturn, hit boxes, camera
#   public/scene/sky.webp     the stars, nebula and moons all round, for the live scene's background
#   src/data/cabin.json       where each prop sits in the still, for the hotspots
#   scene/cabin.blend         the scene after baking, for looking around in Blender
# Run from the project root:
#   blender -b --factory-startup -P scene/cabin.py
# FAST=1 bakes and renders at lower quality for quick looks.
# Re-running overwrites everything above, so change this script, not the .blend.

import inspect
import json
import math
import os
import random

import bmesh
import bpy
import io_scene_gltf2.io.exp.meshopt as gltf_meshopt
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector, noise

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FAST = os.environ.get("FAST") == "1"
CAMERA = Vector((0, -5.5, 3.0))
CAMERA_TARGET = Vector((0, 1.0, 1.9))
LENS = 30
WALL_Y = 2.1
DESK_Z = 1.1
WINDOW = {"z": 2.95, "width": 4.4, "height": 1.9, "radius": 0.35}
# Where the blinking light outside appears on the window, as (x, z) on the back
# wall: up and to the left of Saturn, and between the side panels at the window.
BEACON = (-0.7, 3.72)
# The wall socket everything's plugged into, on the back wall above the desk,
# between the laptop and the pen cup.
OUTLET = (0.62, 1.25)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0
scene = bpy.context.scene


# ---------------------------------------------------------------- helpers

def activate(obj):
	for other in bpy.context.selected_objects:
		other.select_set(False)
	obj.select_set(True)
	bpy.context.view_layer.objects.active = obj


def finish(obj, mat, bevel=0.0, segments=3, smooth=None):
	"""Bake in the scale, round the edges, smooth curved faces, set the material."""
	activate(obj)
	bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
	if bevel:
		mod = obj.modifiers.new("bevel", "BEVEL")
		mod.width = bevel
		mod.segments = segments
		mod.limit_method = "ANGLE"
	if obj.modifiers:
		bpy.ops.object.convert(target="MESH")
	if smooth:
		bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth))
	obj.data.materials.clear()
	obj.data.materials.append(mat)
	return obj


def radians(rotation):
	return [math.radians(a) for a in rotation]


def box(name, center, size, mat, rotation=(0, 0, 0), bevel=0.0, segments=3, parent=None):
	bpy.ops.mesh.primitive_cube_add(size=1, location=center, rotation=radians(rotation))
	obj = bpy.context.object
	obj.name = name
	obj.scale = size
	obj.parent = parent
	return finish(obj, mat, bevel, segments, smooth=30 if bevel else None)


def cylinder(name, center, radius, depth, mat, rotation=(0, 0, 0), bevel=0.0, vertices=48, parent=None):
	bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=center, rotation=radians(rotation))
	obj = bpy.context.object
	obj.name = name
	obj.parent = parent
	return finish(obj, mat, bevel, smooth=40)


def cone(name, center, bottom, top, depth, mat):
	bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=bottom, radius2=top, depth=depth, location=center)
	obj = bpy.context.object
	obj.name = name
	return finish(obj, mat, 0.01, smooth=40)


def sphere(name, center, radius, mat, scale=(1, 1, 1), rotation=(0, 0, 0), segments=32, parent=None):
	bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=segments // 2, radius=radius, location=center, rotation=radians(rotation))
	obj = bpy.context.object
	obj.name = name
	obj.scale = scale
	obj.parent = parent
	return finish(obj, mat, smooth=80)


def torus(name, center, major, minor, mat, rotation=(0, 0, 0), parent=None):
	bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=64, minor_segments=16, location=center, rotation=radians(rotation))
	obj = bpy.context.object
	obj.name = name
	obj.parent = parent
	return finish(obj, mat, smooth=80)


def rod(name, start, end, radius, mat, vertices=16, parent=None):
	"""A cylinder from one point to another."""
	start, end = Vector(start), Vector(end)
	direction = end - start
	bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=direction.length, location=(start + end) / 2)
	obj = bpy.context.object
	obj.name = name
	obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
	obj.parent = parent
	return finish(obj, mat, smooth=40)


FONTS = os.path.join(ROOT, "scene", "assets", "fonts")
loaded_fonts = {}


def font(name, file):
	"""A downloaded font (run scene/fetch-assets.sh first)."""
	if name not in loaded_fonts:
		loaded_fonts[name] = bpy.data.fonts.load(os.path.join(FONTS, name, file))
	return loaded_fonts[name]


def stencil(name, text, location, facing, size, mat, align="CENTER", resolution=3, typeface=None, spin=0.0):
	"""Lettering on a surface. facing is the surface's normal; on a wall the
	text reads left to right for someone looking at it, on a flat surface it
	reads from the front of the desk. spin turns it in its own plane, in degrees."""
	normal = Vector(facing).normalized()
	if abs(normal.z) > 0.9:
		across = Vector((1, 0, 0))
	else:
		across = Vector((0, 0, 1)).cross(normal).normalized()
	up = normal.cross(across)
	bpy.ops.object.text_add(location=location)
	obj = bpy.context.object
	obj.name = name
	obj.rotation_euler = (Matrix.Rotation(-math.radians(spin), 3, normal) @ Matrix((across, up, normal)).transposed()).to_euler()
	if typeface:
		obj.data.font = typeface
	obj.data.body = text
	obj.data.size = size
	obj.data.align_x = align
	obj.data.resolution_u = resolution
	obj.data.align_y = "CENTER"
	activate(obj)
	bpy.ops.object.convert(target="MESH")
	# Lettering is paint or ink: flat, with its flat areas simplified.
	simplify = obj.modifiers.new("simplify", "DECIMATE")
	simplify.decimate_type = "DISSOLVE"
	simplify.angle_limit = math.radians(5)
	bpy.ops.object.convert(target="MESH")
	obj.data.materials.clear()
	obj.data.materials.append(mat)
	return obj


def cut(target, cutter):
	"""Subtract cutter from target, then delete the cutter."""
	mod = target.modifiers.new("cut", "BOOLEAN")
	mod.operation = "DIFFERENCE"
	mod.object = cutter
	activate(target)
	bpy.ops.object.convert(target="MESH")
	bpy.data.objects.remove(cutter)
	return target


# ---------------------------------------------------------------- materials

def find_socket(sockets, name, kind):
	"""Some nodes have several sockets with one name, one per data type."""
	return next(socket for socket in sockets if socket.name == name and socket.type == kind and socket.enabled)


def mix_colour(nodes, links, factor, a, b):
	"""a where factor is 0, b where it's 1. a and b are sockets or RGB tuples."""
	mix = nodes.new("ShaderNodeMix")
	mix.data_type = "RGBA"
	links.new(factor, find_socket(mix.inputs, "Factor", "VALUE"))
	for name, value in (("A", a), ("B", b)):
		socket = find_socket(mix.inputs, name, "RGBA")
		if isinstance(value, tuple):
			socket.default_value = (*value, 1)
		else:
			links.new(value, socket)
	return find_socket(mix.outputs, "Result", "RGBA")


def scale_colour(nodes, links, colour, factor):
	scale = nodes.new("ShaderNodeVectorMath")
	scale.operation = "SCALE"
	links.new(colour, scale.inputs[0])
	scale.inputs["Scale"].default_value = factor
	return scale.outputs["Vector"]


def math_node(nodes, links, operation, a, b=None):
	node = nodes.new("ShaderNodeMath")
	node.operation = operation
	for socket, value in ((node.inputs[0], a), (node.inputs[1], b)):
		if value is None:
			continue
		if isinstance(value, (int, float)):
			socket.default_value = value
		else:
			links.new(value, socket)
	return node.outputs[0]


TEXTURES = os.path.join(ROOT, "scene", "assets", "textures")
loaded_images = {}


def photo_image(texture, kind):
	"""One map of a downloaded ambientCG texture (run scene/fetch-assets.sh first)."""
	path = os.path.join(TEXTURES, texture, f"{texture}_1K-JPG_{kind}.jpg")
	if path not in loaded_images:
		image = bpy.data.images.load(path)
		image.colorspace_settings.name = "sRGB" if kind == "Color" else "Non-Color"
		loaded_images[path] = image
	return loaded_images[path]


def triplanar(nodes, links, image, size):
	"""Samples an image along all three world axes and blends them by which way
	the surface faces, so a photo wraps any shape without UVs, and lands the
	same on separate objects (the still) and joined ones (the bake). size is
	how many units one repeat of the image covers."""
	geometry = nodes.new("ShaderNodeNewGeometry")
	scaled = nodes.new("ShaderNodeVectorMath")
	scaled.operation = "SCALE"
	scaled.inputs["Scale"].default_value = 1 / size
	links.new(geometry.outputs["Position"], scaled.inputs[0])
	position = nodes.new("ShaderNodeSeparateXYZ")
	links.new(scaled.outputs["Vector"], position.inputs[0])
	facing = nodes.new("ShaderNodeSeparateXYZ")
	links.new(geometry.outputs["Normal"], facing.inputs[0])
	weights = {
		axis: math_node(nodes, links, "POWER", math_node(nodes, links, "ABSOLUTE", facing.outputs[axis]), 4)
		for axis in ("X", "Y", "Z")
	}
	total = math_node(nodes, links, "ADD", math_node(nodes, links, "ADD", weights["X"], weights["Y"]), weights["Z"])
	blended = None
	for axis, (u, v) in {"X": ("Y", "Z"), "Y": ("X", "Z"), "Z": ("X", "Y")}.items():
		flat = nodes.new("ShaderNodeCombineXYZ")
		links.new(position.outputs[u], flat.inputs["X"])
		links.new(position.outputs[v], flat.inputs["Y"])
		sample = nodes.new("ShaderNodeTexImage")
		sample.image = image
		links.new(flat.outputs["Vector"], sample.inputs["Vector"])
		share = nodes.new("ShaderNodeVectorMath")
		share.operation = "SCALE"
		links.new(sample.outputs["Color"], share.inputs[0])
		links.new(math_node(nodes, links, "DIVIDE", weights[axis], total), share.inputs["Scale"])
		if blended is None:
			blended = share.outputs["Vector"]
		else:
			add = nodes.new("ShaderNodeVectorMath")
			add.operation = "ADD"
			links.new(blended, add.inputs[0])
			links.new(share.outputs["Vector"], add.inputs[1])
			blended = add.outputs["Vector"]
	return blended


def vector_op(nodes, links, operation, a, b):
	node = nodes.new("ShaderNodeVectorMath")
	node.operation = operation
	for socket, value in ((node.inputs[0], a), (node.inputs[1], b)):
		if isinstance(value, tuple):
			socket.default_value = value
		else:
			links.new(value, socket)
	return node.outputs["Vector"]


def mask_of(nodes, links, texture, size):
	"""A greyscale overlay (grime, scratches, fingerprints) as a 0..1 value."""
	return first_channel(nodes, links, triplanar(nodes, links, photo_image(texture, "Opacity"), size))


def first_channel(nodes, links, vector):
	separate = nodes.new("ShaderNodeSeparateXYZ")
	links.new(vector, separate.inputs[0])
	return separate.outputs["X"]


def material(
	name, color, rough=0.5, metal=0.0, emit=None, strength=1.0,
	grain=0.0, grain_scale=6.0, stretch=(1, 1, 1), bump=0.0, bump_scale=60.0, dirt=0.0, pattern=None,
	photo=None, photo_size=1.0, photo_bump=0.0, grime=0.0, scratches=0.0, prints=0.0, dust=0.0,
):
	"""A Principled material with optional surface detail, all driven by world
	position so it's the same in the still (separate objects) and the bake (one
	joined object).

	photo is a downloaded texture whose colour is tinted by color and whose
	height map gives photo_bump relief; photo_size is the size of one repeat.
	Without a photo, grain varies the colour and bump roughens the surface;
	stretch smears both along an axis, for brushed metal and wood.
	On top of either: pattern draws something (a grid, stripes); grime darkens
	in streaks; scratches lighten in fine lines; prints adds fingerprints; dust
	settles on upward-facing surfaces; dirt darkens creases and corners."""
	mat = bpy.data.materials.new(name)
	nodes = mat.node_tree.nodes
	links = mat.node_tree.links
	bsdf = nodes["Principled BSDF"]
	bsdf.inputs["Base Color"].default_value = (*color, 1)
	bsdf.inputs["Roughness"].default_value = rough
	bsdf.inputs["Metallic"].default_value = metal
	if emit:
		bsdf.inputs["Emission Color"].default_value = (*emit, 1)
		bsdf.inputs["Emission Strength"].default_value = strength
		return mat
	geometry = nodes.new("ShaderNodeNewGeometry")
	position = geometry.outputs["Position"]
	if stretch != (1, 1, 1):
		smear = nodes.new("ShaderNodeVectorMath")
		smear.operation = "MULTIPLY"
		smear.inputs[1].default_value = stretch
		links.new(position, smear.inputs[0])
		position = smear.outputs["Vector"]
	rgb = nodes.new("ShaderNodeRGB")
	rgb.outputs[0].default_value = (*color, 1)
	colour = rgb.outputs[0]
	if photo:
		colour = vector_op(nodes, links, "MULTIPLY", triplanar(nodes, links, photo_image(photo, "Color"), photo_size), tuple(color))
	elif grain:
		noise = nodes.new("ShaderNodeTexNoise")
		noise.inputs["Scale"].default_value = grain_scale
		noise.inputs["Detail"].default_value = 10
		ramp = nodes.new("ShaderNodeValToRGB")
		ramp.color_ramp.elements[0].position = 0.3
		ramp.color_ramp.elements[0].color = (*[c * (1 - grain) for c in color], 1)
		ramp.color_ramp.elements[1].position = 0.7
		ramp.color_ramp.elements[1].color = (*[min(1, c * (1 + grain)) for c in color], 1)
		links.new(position, noise.inputs["Vector"])
		links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
		colour = ramp.outputs["Color"]
	if pattern:
		colour = pattern(nodes, links, colour, geometry.outputs["Position"])
	if grime:
		streaks = mask_of(nodes, links, "SurfaceImperfections003", 1.6)
		colour = mix_colour(nodes, links, math_node(nodes, links, "MULTIPLY", streaks, grime), colour, (0.04, 0.035, 0.03))
	if scratches:
		# The scratch photo is faint (nearly all of it under a quarter), so it's
		# boosted: scratches of 0.1 to 0.3 show as light to heavy wear.
		lines = mask_of(nodes, links, "Scratches005", 0.8)
		colour = mix_colour(nodes, links, math_node(nodes, links, "MULTIPLY", lines, scratches * 10), colour, (0.7, 0.7, 0.68))
	if prints:
		smudges = mask_of(nodes, links, "Fingerprints002", 0.35)
		colour = mix_colour(nodes, links, math_node(nodes, links, "MULTIPLY", smudges, prints), colour, (0.5, 0.48, 0.45))
	if dust:
		facing = nodes.new("ShaderNodeSeparateXYZ")
		links.new(geometry.outputs["Normal"], facing.inputs[0])
		upward = nodes.new("ShaderNodeMapRange")
		upward.inputs["From Min"].default_value = 0.6
		upward.inputs["From Max"].default_value = 0.95
		links.new(facing.outputs["Z"], upward.inputs["Value"])
		patches = nodes.new("ShaderNodeTexNoise")
		patches.inputs["Scale"].default_value = 6
		patches.inputs["Detail"].default_value = 8
		links.new(geometry.outputs["Position"], patches.inputs["Vector"])
		settled = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "MULTIPLY", upward.outputs["Result"], patches.outputs["Fac"]), dust)
		colour = mix_colour(nodes, links, settled, colour, (0.42, 0.4, 0.36))
	if dirt:
		occlusion = nodes.new("ShaderNodeAmbientOcclusion")
		occlusion.samples = 16
		occlusion.inputs["Distance"].default_value = 0.4
		colour = mix_colour(nodes, links, occlusion.outputs["AO"], scale_colour(nodes, links, colour, 1 - dirt), colour)
	links.new(colour, bsdf.inputs["Base Color"])
	height = None
	if photo and photo_bump:
		height = first_channel(nodes, links, triplanar(nodes, links, photo_image(photo, "Displacement"), photo_size))
		strength_of_relief = photo_bump
	elif bump:
		noise = nodes.new("ShaderNodeTexNoise")
		noise.inputs["Scale"].default_value = bump_scale
		noise.inputs["Detail"].default_value = 6
		links.new(position, noise.inputs["Vector"])
		height = noise.outputs["Fac"]
		strength_of_relief = bump
	if height is not None:
		relief = nodes.new("ShaderNodeBump")
		relief.inputs["Strength"].default_value = strength_of_relief
		relief.inputs["Distance"].default_value = 0.005
		links.new(height, relief.inputs["Height"])
		links.new(relief.outputs["Normal"], bsdf.inputs["Normal"])
	return mat


def grid(spacing, width, line, axes=("X", "Y")):
	"""Pattern: thin lines every spacing units along the given axes: a cutting
	mat on the desk, panel seams on the walls."""
	def build(nodes, links, colour, position):
		separate = nodes.new("ShaderNodeSeparateXYZ")
		links.new(position, separate.inputs[0])
		on_line = [
			math_node(nodes, links, "LESS_THAN", math_node(nodes, links, "FRACT", math_node(nodes, links, "MULTIPLY", separate.outputs[axis], 1 / spacing)), width / spacing)
			for axis in axes
		]
		while len(on_line) > 1:
			on_line = [math_node(nodes, links, "MAXIMUM", on_line[0], on_line[1])] + on_line[2:]
		return mix_colour(nodes, links, on_line[0], colour, line)
	return build


def bands(axis, scale, low, high, wobble=4.0):
	"""Pattern: wavy stripes across one axis, for wood grain and leaves. low and
	high scale the colour at the dark and light edges of each stripe."""
	def build(nodes, links, colour, position):
		wave = nodes.new("ShaderNodeTexWave")
		wave.wave_type = "BANDS"
		wave.bands_direction = axis
		wave.inputs["Scale"].default_value = scale
		wave.inputs["Distortion"].default_value = wobble
		wave.inputs["Detail"].default_value = 4
		ramp = nodes.new("ShaderNodeValToRGB")
		ramp.color_ramp.elements[0].color = (low, low, low, 1)
		ramp.color_ramp.elements[1].color = (high, high, high, 1)
		multiply = nodes.new("ShaderNodeVectorMath")
		multiply.operation = "MULTIPLY"
		links.new(position, wave.inputs["Vector"])
		links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
		links.new(colour, multiply.inputs[0])
		links.new(ramp.outputs["Color"], multiply.inputs[1])
		return multiply.outputs["Vector"]
	return build


def hazard(width):
	"""Pattern: diagonal stripes width wide, black over the colour, like hazard tape."""
	def build(nodes, links, colour, position):
		separate = nodes.new("ShaderNodeSeparateXYZ")
		links.new(position, separate.inputs[0])
		diagonal = math_node(nodes, links, "ADD", separate.outputs["X"], separate.outputs["Z"])
		black = math_node(nodes, links, "LESS_THAN", math_node(nodes, links, "FRACT", math_node(nodes, links, "MULTIPLY", diagonal, 1 / (2 * width))), 0.5)
		return mix_colour(nodes, links, black, colour, (0.02, 0.02, 0.02))
	return build


def layers(*patterns):
	"""Patterns drawn one over another."""
	def build(nodes, links, colour, position):
		for pattern in patterns:
			colour = pattern(nodes, links, colour, position)
		return colour
	return build


def runs_down(nodes, links, position, points, width, length):
	"""0..1: a narrow streak run down from each (x, z) point, fading as it goes."""
	separate = nodes.new("ShaderNodeSeparateXYZ")
	links.new(position, separate.inputs[0])
	runs = None
	for x, z in points:
		dx = math_node(nodes, links, "SUBTRACT", separate.outputs["X"], x)
		across = math_node(nodes, links, "EXPONENT", math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "MULTIPLY", dx, dx), -1 / width ** 2))
		below = math_node(nodes, links, "SUBTRACT", z, separate.outputs["Z"])
		fade = math_node(nodes, links, "MAXIMUM", math_node(nodes, links, "SUBTRACT", 1, math_node(nodes, links, "DIVIDE", below, length)), 0)
		run = math_node(nodes, links, "MULTIPLY", across, math_node(nodes, links, "MULTIPLY", fade, math_node(nodes, links, "GREATER_THAN", below, 0)))
		runs = run if runs is None else math_node(nodes, links, "MAXIMUM", runs, run)
	return runs


def drip(x, front, top, length, stain):
	"""Pattern: a dribble run down from top at x, on the side nearer the camera than front (a y)."""
	def build(nodes, links, colour, position):
		separate = nodes.new("ShaderNodeSeparateXYZ")
		links.new(position, separate.inputs[0])
		facing = math_node(nodes, links, "LESS_THAN", separate.outputs["Y"], front)
		run = math_node(nodes, links, "MULTIPLY", runs_down(nodes, links, position, [(x, top)], 0.02, length), facing)
		return mix_colour(nodes, links, math_node(nodes, links, "MULTIPLY", run, 0.85), colour, stain)
	return build


def zone(nodes, links, separate, x, y, radius, squash=1.0):
	"""0..1: highest at (x, y) on a flat surface, fading out over radius (over radius / squash across y)."""
	dx = math_node(nodes, links, "SUBTRACT", separate.outputs["X"], x)
	dy = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "SUBTRACT", separate.outputs["Y"], y), squash)
	square = math_node(nodes, links, "ADD", math_node(nodes, links, "MULTIPLY", dx, dx), math_node(nodes, links, "MULTIPLY", dy, dy))
	return math_node(nodes, links, "EXPONENT", math_node(nodes, links, "MULTIPLY", square, -1 / radius ** 2))


def crumbs(zones):
	"""Pattern: biscuit crumbs, thickest in the middle of each (x, y, radius)
	zone, each crumb its own size and shade."""
	def build(nodes, links, colour, position):
		separate = nodes.new("ShaderNodeSeparateXYZ")
		links.new(position, separate.inputs[0])
		near = None
		for x, y, radius in zones:
			here = zone(nodes, links, separate, x, y, radius)
			near = here if near is None else math_node(nodes, links, "MAXIMUM", near, here)
		cells = nodes.new("ShaderNodeTexVoronoi")
		cells.inputs["Scale"].default_value = 70
		links.new(position, cells.inputs["Vector"])
		chance = nodes.new("ShaderNodeSeparateXYZ")
		links.new(cells.outputs["Color"], chance.inputs[0])
		kept = math_node(nodes, links, "LESS_THAN", chance.outputs["X"], math_node(nodes, links, "MULTIPLY", near, 0.55))
		size = math_node(nodes, links, "ADD", 0.1, math_node(nodes, links, "MULTIPLY", chance.outputs["Y"], 0.22))
		crumb = math_node(nodes, links, "MULTIPLY", kept, math_node(nodes, links, "LESS_THAN", cells.outputs["Distance"], size))
		shade = mix_colour(nodes, links, chance.outputs["Z"], (0.55, 0.36, 0.16), (0.3, 0.19, 0.08))
		return mix_colour(nodes, links, crumb, colour, shade)
	return build


def rubbed(x, y, radius, amount):
	"""Pattern: a patch worn paler by hands and wrists, wider than it is deep."""
	def build(nodes, links, colour, position):
		separate = nodes.new("ShaderNodeSeparateXYZ")
		links.new(position, separate.inputs[0])
		worn = math_node(nodes, links, "MULTIPLY", zone(nodes, links, separate, x, y, radius, squash=2.0), amount)
		return mix_colour(nodes, links, worn, colour, scale_colour(nodes, links, colour, 1.35))
	return build


def efflorescence(bottom, top):
	"""Pattern for unglazed clay: darker where water has soaked up from the
	bottom, and a white mineral crust in patches above that and under the rim."""
	def build(nodes, links, colour, position):
		separate = nodes.new("ShaderNodeSeparateXYZ")
		links.new(position, separate.inputs[0])
		height = math_node(nodes, links, "DIVIDE", math_node(nodes, links, "SUBTRACT", separate.outputs["Z"], bottom), top - bottom)
		wet = nodes.new("ShaderNodeMapRange")
		wet.inputs["From Min"].default_value = 0.14
		wet.inputs["From Max"].default_value = 0.0
		links.new(height, wet.inputs["Value"])
		patches = nodes.new("ShaderNodeTexNoise")
		patches.inputs["Scale"].default_value = 12
		patches.inputs["Detail"].default_value = 6
		links.new(position, patches.inputs["Vector"])
		spread = nodes.new("ShaderNodeMapRange")
		spread.inputs["From Min"].default_value = 0.45
		spread.inputs["From Max"].default_value = 0.62
		links.new(patches.outputs["Fac"], spread.inputs["Value"])
		bands = None
		for middle, width in ((0.18, 0.07), (0.8, 0.09)):
			off = math_node(nodes, links, "SUBTRACT", height, middle)
			band = math_node(nodes, links, "EXPONENT", math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "MULTIPLY", off, off), -1 / width ** 2))
			bands = band if bands is None else math_node(nodes, links, "MAXIMUM", bands, band)
		crust = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "MULTIPLY", bands, spread.outputs["Result"]), 0.8)
		colour = mix_colour(nodes, links, math_node(nodes, links, "MULTIPLY", wet.outputs["Result"], 0.85), colour, scale_colour(nodes, links, colour, 0.5))
		return mix_colour(nodes, links, crust, colour, (0.82, 0.8, 0.72))
	return build


def scorch(x, z, radius):
	"""Pattern: soot from an overheating socket at (x, z) on a wall, rising
	above it in a ragged plume."""
	def build(nodes, links, colour, position):
		separate = nodes.new("ShaderNodeSeparateXYZ")
		links.new(position, separate.inputs[0])
		dx = math_node(nodes, links, "DIVIDE", math_node(nodes, links, "SUBTRACT", separate.outputs["X"], x), radius * 0.6)
		up = math_node(nodes, links, "DIVIDE", math_node(nodes, links, "SUBTRACT", separate.outputs["Z"], z + radius * 0.6), radius * 1.4)
		square = math_node(nodes, links, "ADD", math_node(nodes, links, "MULTIPLY", dx, dx), math_node(nodes, links, "MULTIPLY", up, up))
		plume = math_node(nodes, links, "EXPONENT", math_node(nodes, links, "MULTIPLY", square, -1))
		ragged = nodes.new("ShaderNodeTexNoise")
		ragged.inputs["Scale"].default_value = 18
		ragged.inputs["Detail"].default_value = 8
		links.new(position, ragged.inputs["Vector"])
		soot = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "MULTIPLY", plume, ragged.outputs["Fac"]), 2.2)
		return mix_colour(nodes, links, math_node(nodes, links, "MINIMUM", soot, 0.9), colour, (0.05, 0.035, 0.025))
	return build


def speckle(scale, size, dot):
	"""Pattern: small dots, like a speckled glaze."""
	def build(nodes, links, colour, position):
		cells = nodes.new("ShaderNodeTexVoronoi")
		cells.inputs["Scale"].default_value = scale
		links.new(position, cells.inputs["Vector"])
		return mix_colour(nodes, links, math_node(nodes, links, "LESS_THAN", cells.outputs["Distance"], size), colour, dot)
	return build


def worn_paint(name, paint, bare_tint, bare="Wood096", bare_size=0.5, rust=None, scratches=0.5, scratched=(0.5, 0.45, 0.38)):
	"""Paint worn through to what's under it (bare wood, or a metal's photo):
	chipped, rubbed off at the edges, scratched (to the scratched colour; the
	scratch photo is faint, so scratches above 1 are still subtle), and grimy. rust is a list of (x, z) points, like bolts, that rust has run down from."""
	mat = bpy.data.materials.new(name)
	nodes = mat.node_tree.nodes
	links = mat.node_tree.links
	bsdf = nodes["Principled BSDF"]
	bsdf.inputs["Roughness"].default_value = 0.45
	under = vector_op(nodes, links, "MULTIPLY", triplanar(nodes, links, photo_image(bare, "Color"), bare_size), bare_tint)
	# Chips: the bare patches of the chipped-paint photo, which are darker than its paint.
	chips_photo = first_channel(nodes, links, triplanar(nodes, links, photo_image("PaintedMetal012", "Color"), 0.9))
	chips = nodes.new("ShaderNodeMapRange")
	chips.inputs["From Min"].default_value = 0.62
	chips.inputs["From Max"].default_value = 0.45
	links.new(chips_photo, chips.inputs["Value"])
	# Edges: where the mesh is thin, ambient occlusion looking inwards is low.
	inside = nodes.new("ShaderNodeAmbientOcclusion")
	inside.inside = True
	inside.samples = 16
	inside.inputs["Distance"].default_value = 0.05
	edges = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "SUBTRACT", 1, inside.outputs["AO"]), 2.2)
	worn = math_node(nodes, links, "MINIMUM", math_node(nodes, links, "MAXIMUM", chips.outputs["Result"], edges), 1)
	colour = mix_colour(nodes, links, worn, paint, under)
	lines = mask_of(nodes, links, "Scratches005", 0.5)
	colour = mix_colour(nodes, links, math_node(nodes, links, "MULTIPLY", lines, scratches), colour, scratched)
	streaks = mask_of(nodes, links, "SurfaceImperfections003", 0.8)
	colour = mix_colour(nodes, links, math_node(nodes, links, "MULTIPLY", streaks, 0.3), colour, (0.04, 0.035, 0.03))
	if rust:
		position = nodes.new("ShaderNodeNewGeometry").outputs["Position"]
		breakup = nodes.new("ShaderNodeTexNoise")
		breakup.inputs["Detail"].default_value = 6
		links.new(vector_op(nodes, links, "MULTIPLY", position, (50, 50, 5)), breakup.inputs["Vector"])
		patchy = nodes.new("ShaderNodeMapRange")
		patchy.inputs["From Min"].default_value = 0.35
		patchy.inputs["From Max"].default_value = 0.65
		patchy.inputs["To Min"].default_value = 0.2
		links.new(breakup.outputs["Fac"], patchy.inputs["Value"])
		runs = math_node(nodes, links, "MULTIPLY", runs_down(nodes, links, position, rust, 0.02, 0.32), patchy.outputs["Result"])
		colour = mix_colour(nodes, links, math_node(nodes, links, "MULTIPLY", runs, 0.75), colour, (0.25, 0.1, 0.035))
	links.new(colour, bsdf.inputs["Base Color"])
	return mat


def smudged_glow(name, glow, strength, prints, size=0.35):
	"""A lit screen with greasy fingerprints on it, hazy where they are."""
	mat = material(name, (0, 0, 0), emit=glow, strength=strength)
	nodes = mat.node_tree.nodes
	links = mat.node_tree.links
	smudges = math_node(nodes, links, "MULTIPLY", mask_of(nodes, links, "Fingerprints002", size), prints)
	links.new(mix_colour(nodes, links, smudges, glow, tuple(c * 0.55 + 0.1 for c in glow)), nodes["Principled BSDF"].inputs["Emission Color"])
	return mat


def lathe(name, center, profile, mat, segments=64, wobble=0.0, chip=None):
	"""Something round, turned from a profile of (radius, height) points up the
	outside and back down the inside. wobble makes it look hand-made, a little
	lumpy; chip is the angle, in degrees, where a piece of the rim is broken off."""
	mesh = bmesh.new()
	top = max(z for _, z in profile)
	rings = []
	for radius, z in profile:
		if radius == 0:
			rings.append([mesh.verts.new((0, 0, z))])
			continue
		ring = []
		for j in range(segments):
			angle = 2 * math.pi * j / segments
			r = radius * (1 + wobble * noise.noise(Vector((math.cos(angle) * 1.5, math.sin(angle) * 1.5, z * 8))))
			h = z
			if chip is not None and z > top - 0.03:
				off = abs((angle - math.radians(chip) + math.pi) % (2 * math.pi) - math.pi)
				if off < 0.2:
					h -= 0.024 * (1 - off / 0.2) ** 0.5
			ring.append(mesh.verts.new((r * math.cos(angle), r * math.sin(angle), h)))
		rings.append(ring)
	for low, high in zip(rings, rings[1:]):
		for j in range(segments):
			corners = [low[j % len(low)], low[(j + 1) % len(low)], high[(j + 1) % len(high)], high[j % len(high)]]
			face = [v for i, v in enumerate(corners) if v is not corners[i - 1]]
			mesh.faces.new(face)
	data = bpy.data.meshes.new(name)
	mesh.to_mesh(data)
	mesh.free()
	obj = bpy.data.objects.new(name, data)
	scene.collection.objects.link(obj)
	obj.location = center
	return finish(obj, mat, smooth=50)


def smooth_noise(shape, cells, rng):
	"""Smooth random values from 0 to 1 over a picture, about cells across it."""
	rows, columns = shape
	grid = rng.random((max(2, cells * rows // columns) + 2, cells + 2))
	ys = np.linspace(0, grid.shape[0] - 2.001, rows)
	xs = np.linspace(0, grid.shape[1] - 2.001, columns)
	y0, x0 = ys.astype(int), xs.astype(int)
	fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
	fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
	upper = grid[y0][:, x0] * (1 - fx) + grid[y0][:, x0 + 1] * fx
	lower = grid[y0 + 1][:, x0] * (1 - fx) + grid[y0 + 1][:, x0 + 1] * fx
	return upper * (1 - fy) + lower * fy


def smooth_loop(points, per_segment=8):
	"""A closed Catmull-Rom curve through the points, as a list of points."""
	out = []
	count = len(points)
	for i in range(count):
		p0, p1, p2, p3 = (Vector(points[(i + k) % count]) for k in (-1, 0, 1, 2))
		for step in range(per_segment):
			t = step / per_segment
			out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
	return out


def ramp_material(name, stops, rough, coordinate, alpha=False, emission=0.0, pattern=None):
	"""A colour ramp driven by a scalar built from the shading point."""
	mat = bpy.data.materials.new(name)
	nodes = mat.node_tree.nodes
	links = mat.node_tree.links
	bsdf = nodes["Principled BSDF"]
	bsdf.inputs["Roughness"].default_value = rough
	ramp = nodes.new("ShaderNodeValToRGB")
	elements = ramp.color_ramp.elements
	for i, (position, color, a) in enumerate(stops):
		element = elements[i] if i < 2 else elements.new(position)
		element.position = position
		element.color = (*color, a)
	links.new(coordinate(nodes, links), ramp.inputs["Fac"])
	colour = ramp.outputs["Color"]
	if pattern:
		colour = pattern(nodes, links, colour, nodes.new("ShaderNodeNewGeometry").outputs["Position"])
	links.new(colour, bsdf.inputs["Base Color"])
	if emission:
		links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
		bsdf.inputs["Emission Strength"].default_value = emission
	if alpha:
		links.new(ramp.outputs["Alpha"], bsdf.inputs["Alpha"])
	return mat


def distance_from(center, near, far):
	"""Coordinate: distance from a world point, mapped from near..far to 0..1."""
	def build(nodes, links):
		geometry = nodes.new("ShaderNodeNewGeometry")
		subtract = nodes.new("ShaderNodeVectorMath")
		subtract.operation = "SUBTRACT"
		subtract.inputs[1].default_value = center
		length = nodes.new("ShaderNodeVectorMath")
		length.operation = "LENGTH"
		remap = nodes.new("ShaderNodeMapRange")
		remap.inputs["From Min"].default_value = near
		remap.inputs["From Max"].default_value = far
		links.new(geometry.outputs["Position"], subtract.inputs[0])
		links.new(subtract.outputs["Vector"], length.inputs[0])
		links.new(length.outputs["Value"], remap.inputs["Value"])
		return remap.outputs["Result"]
	return build


cream = material(
	"cream-panel", (0.86, 0.79, 0.67), rough=0.55, photo="PaintedMetal012", photo_size=2.7, photo_bump=0.25, grime=0.4, dirt=0.5,
	pattern=layers(grid(1.5, 0.012, (0.3, 0.27, 0.22), axes=("X", "Y", "Z")), scorch(OUTLET[0] + 0.33, OUTLET[1], 0.2)),
)
charcoal = material("charcoal", (0.3, 0.3, 0.32), rough=0.6, photo="DiamondPlate009", photo_size=0.8, photo_bump=0.6, grime=0.3, dust=0.2, dirt=0.4)
rib = material("rib", (0.28, 0.28, 0.3), rough=0.45, photo="Metal038", photo_size=0.9, photo_bump=0.15, scratches=0.15, grime=0.25, dirt=0.35)
# The desk mat: its grid, a patch rubbed pale in front of the laptop, and
# crumbs round the biscuit, in front of the mug and in front of the keyboard.
mat_black = material(
	"desk-mat", (0.45, 0.48, 0.48), rough=0.8, photo="Rubber004", photo_size=0.9, photo_bump=0.2, dust=0.35, grime=0.15, dirt=0.3,
	pattern=layers(
		grid(0.25, 0.006, (0.06, 0.068, 0.068)),
		rubbed(-0.45, -0.3, 0.5, 0.6),
		crumbs([(1.15, -0.05, 0.3), (0.6, 0.0, 0.18), (-0.45, -0.12, 0.3)]),
	),
)
orange = material("accent-orange", (0.86, 0.28, 0.07), rough=0.4, photo="PaintedMetal012", photo_size=1.2, photo_bump=0.2, grime=0.2, dirt=0.3)
steel = material("steel", (0.9, 0.9, 0.95), rough=0.35, metal=0.6, photo="Metal038", photo_size=0.5, scratches=0.2)
aluminium = material("aluminium", (1.05, 1.06, 1.1), rough=0.35, photo="Metal009", photo_size=0.6, prints=0.35, scratches=0.1)
key_black = material("keys", (0.025, 0.025, 0.03), rough=0.5, grain=0.1, grain_scale=40, dust=0.25, dirt=0.3)
glass_black = material("bezel", (0.01, 0.01, 0.012), rough=0.15)
# A coffee drip down the front of the mug, from the rim.
glaze = material(
	"mug-glaze", (0.6, 0.16, 0.04), rough=0.25, bump=0.03, bump_scale=250, dirt=0.2,
	pattern=layers(speckle(120, 0.12, (0.25, 0.06, 0.02)), drip(0.71, 0.2, DESK_Z + 0.36, 0.16, (0.09, 0.035, 0.012))),
)
coffee = material("coffee", (0.05, 0.022, 0.01), rough=0.1)
phone_body = material("phone-body", (0.05, 0.05, 0.06), rough=0.3, photo="Plastic013A", photo_size=0.5, scratches=0.12, prints=0.3)
# A dark lock screen in the still; the live scene draws what's playing.
phone_glow = smudged_glow("phone-screen", (0.02, 0.05, 0.08), 1.0, 0.15)
headphone_black = material("headphones", (0.06, 0.06, 0.065), rough=0.45, photo="Plastic013A", photo_size=0.6, scratches=0.12, dirt=0.3)
cushion = material("cushion", (0.35, 0.33, 0.33), rough=0.9, photo="Leather037", photo_size=0.4, photo_bump=0.4)
terracotta = material("terracotta", (1.0, 0.55, 0.38), rough=0.85, photo="Clay005", photo_size=0.5, photo_bump=0.3, dirt=0.45, pattern=efflorescence(DESK_Z, DESK_Z + 0.33))
# Dry, with white grains of perlite in it.
soil = material("soil", (0.1, 0.065, 0.04), rough=1.0, grain=0.4, grain_scale=80, bump=0.5, bump_scale=150, pattern=speckle(40, 0.15, (0.8, 0.78, 0.72)))
leaf = material("leaf", (0.09, 0.3, 0.1), rough=0.5, grain=0.2, grain_scale=9, pattern=bands("Z", 30, 0.65, 1.25, wobble=6))
led_green = material("led-green", (0, 0, 0), emit=(0.2, 1.0, 0.35), strength=4)
led_amber = material("led-amber", (0, 0, 0), emit=(1.0, 0.55, 0.1), strength=4)
led_red = material("led-red", (0, 0, 0), emit=(1.0, 0.12, 0.08), strength=4)
nickel = material("nickel", (0.7, 0.7, 0.68), rough=0.25, metal=0.8)
lamp_panel = material("lamp-panel", (0, 0, 0), emit=(1.0, 0.75, 0.5), strength=1.2)

# ---------------------------------------------------------------- the room

back = box("back-wall", (0, WALL_Y, 2.5), (9.4, 0.2, 5), cream)
# A little bigger than the frame's opening, and hidden by the frame: if the two
# holes matched, their inner faces would overlap and flicker against each other.
window_hole = box("window-cutter", (0, WALL_Y, WINDOW["z"]), (WINDOW["width"] + 0.08, 1, WINDOW["height"] + 0.08), cream, bevel=WINDOW["radius"] + 0.04, segments=10)
cut(back, window_hole)
# The room runs well forward of the camera, so looking around never reaches its open end.
ROOM_FRONT = -8.2
room_length = WALL_Y + 0.1 - ROOM_FRONT
room_mid = (WALL_Y + 0.1 + ROOM_FRONT) / 2
ROOM_CENTER = Vector((0, room_mid, 2.5))
box("wall-left", (-4.8, room_mid, 2.5), (0.2, room_length, 5), cream)
box("wall-right", (4.8, room_mid, 2.5), (0.2, room_length, 5), cream)
box("floor", (0, room_mid, -0.05), (9.8, room_length, 0.1), charcoal)
box("ceiling", (0, room_mid, 5.0), (9.8, room_length, 0.1), cream)

# The ceiling: a light panel over the desk, and beams across.
box("ceiling-light", (0, 0.5, 4.93), (6, 1.4, 0.04), lamp_panel)
for y in (1.6, -1.2, -4.0, -6.8):
	box(f"ceiling-beam-{y}", (0, y, 4.85), (9.6, 0.3, 0.2), rib, bevel=0.03)

# The side walls: ribs, and an orange stripe at desk height all the way round.
for side in (-1, 1):
	for y in (-0.5, -3.3, -6.1):
		box(f"side-rib-{side}-{y}", (side * 4.69, y, 2.5), (0.22, 0.32, 5), rib, bevel=0.03)
	box(f"side-stripe-{side}", (side * 4.69, room_mid, 1.55), (0.02, room_length, 0.06), orange)

# Panel seams and the structural ribs either side of the viewport.
for x in (-3.75, 3.75):
	box(f"seam-{x}", (x, 1.995, 2.5), (0.025, 0.012, 5), rib)
box("seam-low", (0, 1.995, 1.55), (9.4, 0.012, 0.025), rib)
for x in (-2.78, 2.78):
	box(f"rib-{x}", (x, 1.9, 2.5), (0.32, 0.22, 5), rib, bevel=0.03)
	for z in [1.3 + 0.45 * i for i in range(8)]:
		for dx in (-0.09, 0.09):
			sphere(f"rivet-{x}-{z}-{dx}", (x + dx, 1.785, z), 0.022, steel, segments=12)

# The viewport: a rounded frame proud of the wall, bolted on.
# It runs right through the wall, so its hole lines the whole opening.
frame = box("window-frame", (0, 2.0, WINDOW["z"]), (WINDOW["width"] + 0.5, 0.44, WINDOW["height"] + 0.5), rib, bevel=WINDOW["radius"] + 0.2, segments=10)
frame_hole = box("frame-cutter", (0, 2.0, WINDOW["z"]), (WINDOW["width"], 1, WINDOW["height"]), rib, bevel=WINDOW["radius"], segments=10)
cut(frame, frame_hole)
activate(frame)
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))
bolts = [(x, WINDOW["z"] + s * 1.08) for x in (-1.8, -0.6, 0.6, 1.8) for s in (-1, 1)]
bolts += [(s * 2.36, WINDOW["z"] + dz) for s in (-1, 1) for dz in (-0.4, 0.4)]
for i, (x, z) in enumerate(bolts):
	cylinder(f"window-frame-bolt-{i}", (x, 1.77, z), 0.045, 0.04, steel, rotation=(90, 0, 0), bevel=0.01, vertices=6)
# Its paint is scratched, chipped and worn back to the steel at the edges,
# with rust run down from every bolt.
frame.data.materials.clear()
frame.data.materials.append(worn_paint("frame-paint", (0.07, 0.07, 0.075), (0.7, 0.7, 0.72), bare="Metal038", bare_size=0.6, rust=bolts, scratches=3.0, scratched=(0.6, 0.6, 0.62)))

# ---------------------------------------------------------------- the console

box("desk-top", (0, 0.62, DESK_Z - 0.1), (9.4, 2.9, 0.2), mat_black, bevel=0.05, segments=4)
box("desk-front", (0, -0.78, 0.45), (9.4, 0.12, 0.9), cream, bevel=0.02)
box("desk-stripe", (0, -0.85, 0.83), (9.4, 0.02, 0.05), orange)
for i in range(8):
	x = -3.3 + 0.22 * i
	box(f"switch-plate-{i}", (x, -0.845, 0.6), (0.12, 0.02, 0.17), rib, bevel=0.01)
	cylinder(f"switch-lever-{i}", (x, -0.88, 0.62 + (0.02 if i % 3 else -0.02)), 0.012, 0.09, nickel, rotation=(60 if i % 3 else 120, 0, 0), vertices=12)
for i, led in enumerate((led_green, led_green, led_amber, led_green, led_red, led_green)):
	sphere(f"led-{i}", (-1.0 + 0.2 * i, -0.84, 0.62), 0.028, led, segments=12)
for i in range(9):
	box(f"vent-{i}", (2.6, -0.845, 0.34 + 0.055 * i), (0.9, 0.02, 0.025), rib)

# The artificial gravity: a lever between two guards on a hazard-striped plate,
# just under the desk's edge, with a lamp beside it (green on, amber off) and
# its name on the desk's edge above. The lever and lamp are their own objects
# in the live scene, so it can throw the one and light the other. Up is on.
GRAVITY_AT = Vector((-0.6, -0.86, 0.83))
hazard_paint = material("hazard", (0.85, 0.62, 0.05), rough=0.5, pattern=hazard(0.025), scratches=0.2, grime=0.3)
box("gravity-plate", GRAVITY_AT + Vector((0, -0.015, 0)), (0.36, 0.03, 0.18), hazard_paint, bevel=0.008)
for side in (-1, 1):
	box(f"gravity-guard-{side}", GRAVITY_AT + Vector((side * 0.07, -0.06, 0)), (0.02, 0.06, 0.14), hazard_paint, bevel=0.005)
LEVER_PIVOT = GRAVITY_AT + Vector((0, -0.045, 0))
box("gravity-pivot", LEVER_PIVOT, (0.07, 0.03, 0.06), steel, bevel=0.006)
lever_tip = LEVER_PIVOT + Vector((0, -0.5, 0.866)) * 0.15
rod("gravity-lever", LEVER_PIVOT, lever_tip, 0.012, nickel)
sphere("gravity-lever-knob", lever_tip, 0.03, material("lever-knob", (0.6, 0.04, 0.03), rough=0.3), segments=24)
gravity_lamp = sphere("gravity-lamp", GRAVITY_AT + Vector((0.12, -0.035, 0.03)), 0.022, led_green, segments=16)
# Luminous paint, so it reads on the dark edge of the desk.
# The control panel the gravity fault is about, to the right of the lever:
# four coloured buttons that flash a pattern to play back (the page runs the
# game), and a status lamp, amber until the panel's in sync. The buttons and
# lamp are their own objects, so the live scene can light them.
PANEL_AT = Vector((0.25, -0.86, 0.81))
box("simon-plate", PANEL_AT + Vector((0, -0.015, 0)), (0.3, 0.03, 0.22), rib, bevel=0.008)
SIMON = {"red": (1.0, 0.12, 0.08), "green": (0.15, 0.9, 0.25), "blue": (0.15, 0.35, 1.0), "yellow": (1.0, 0.75, 0.1)}
simon_buttons = [
	cylinder(f"simon-{name}", PANEL_AT + Vector((dx, -0.04, dz)), 0.035, 0.02, material(f"simon-{name}", (0, 0, 0), emit=colour, strength=0.6), rotation=(90, 0, 0), bevel=0.006, vertices=32)
	for (name, colour), (dx, dz) in zip(SIMON.items(), ((-0.055, 0.045), (0.055, 0.045), (-0.055, -0.045), (0.055, -0.045)))
]
simon_lamp = sphere("simon-lamp", PANEL_AT + Vector((0.125, -0.035, 0.085)), 0.014, led_amber, segments=12)
stencil("simon-label", "SYNC", (PANEL_AT.x, -0.836, 1.0), (0, -1, 0), 0.055, material("luminous-sync", (0, 0, 0), emit=(0.85, 0.82, 0.62), strength=0.8))
stencil("gravity-label", "GRAVITY", (GRAVITY_AT.x, -0.836, 1.0), (0, -1, 0), 0.055, material("luminous-paint", (0, 0, 0), emit=(0.85, 0.82, 0.62), strength=0.8))

# ---------------------------------------------------------------- the laptop

box("laptop-base", (-0.5, 0.45, DESK_Z + 0.025), (1.3, 0.9, 0.05), aluminium, bevel=0.02)
for row in range(5):
	for col in range(13):
		box(f"laptop-key-{row}-{col}", (-0.5 - 0.528 + 0.088 * col, 0.73 - 0.082 * row, DESK_Z + 0.054), (0.074, 0.068, 0.012), key_black, bevel=0.008)
box("laptop-key-space", (-0.5, 0.73 - 0.082 * 5, DESK_Z + 0.054), (0.5, 0.068, 0.012), key_black, bevel=0.008)
box("laptop-trackpad", (-0.5, 0.13, DESK_Z + 0.051), (0.42, 0.2, 0.004), material("trackpad", (0.45, 0.46, 0.48), rough=0.3), bevel=0.01)
tilt = math.radians(-12)
lid_center = Vector((-0.5, 0.98, 1.55))
lid_front = Vector((0, -math.cos(tilt), -math.sin(tilt)))
box("laptop-lid", lid_center, (1.3, 0.04, 0.85), aluminium, rotation=(-12, 0, 0), bevel=0.02)
box("laptop-bezel", lid_center + lid_front * 0.021, (1.26, 0.004, 0.81), glass_black, rotation=(-12, 0, 0))
# Smudges on the laptop screen: fingerprints near the bottom corners and the
# top edge, where the lid gets pushed about, and a wipe across, but none in
# the middle, where the live scene samples the screen's colour. It's one
# picture, so the live scene lays the same smudges over the posts it draws.
SMUDGE_PIXELS = (512, 320)
width, height = SMUDGE_PIXELS
channels = []
for texture, kind in (("Fingerprints002", "Opacity"), ("Smear004", "Color")):
	photo = photo_image(texture, kind).copy()
	photo.scale(width, height)
	values = np.empty(width * height * 4, np.float32)
	photo.pixels.foreach_get(values)
	bpy.data.images.remove(photo)
	channels.append(values.reshape(height, width, 4)[:, :, 0])
prints, wipes = channels
# Rows run from the bottom of the picture up, as Blender stores them.
U, V = np.meshgrid((np.arange(width) + 0.5) / width, (np.arange(height) + 0.5) / height)
touched = np.maximum.reduce([np.exp(-((U - u) ** 2 + (V - v) ** 2) / spread ** 2) for u, v, spread in ((0.07, 0.08, 0.14), (0.93, 0.08, 0.14), (0.5, 0.97, 0.12))])
wiped = np.exp(-((V - (0.3 + 0.4 * U)) ** 2) / 0.08 ** 2)
clean = 1 - np.exp(-((U - 0.5) ** 2 + (V - 0.5) ** 2) / 0.06 ** 2)
smudge = np.clip(np.maximum(prints * touched * 1.4, wipes ** 2.2 * wiped * 0.4) * clean, 0, 1)
pixels = np.ones((height, width, 4), np.float32)
pixels[:, :, :3] = smudge[:, :, None]
picture = bpy.data.images.new("screen-smudge", width, height)
picture.pixels.foreach_set(pixels.ravel())
smudge_path = os.path.join(ROOT, "public", "scene", "screen-smudge.webp")
os.makedirs(os.path.dirname(smudge_path), exist_ok=True)
picture.filepath_raw = smudge_path
picture.file_format = "WEBP"
picture.save()
bpy.data.images.remove(picture)
smudge_image = bpy.data.images.load(smudge_path)
smudge_image.colorspace_settings.name = "Non-Color"
laptop_glow = material("laptop-screen", (0, 0, 0), emit=(0.035, 0.07, 0.1), strength=1.0)
smudge_texture = laptop_glow.node_tree.nodes.new("ShaderNodeTexImage")
smudge_texture.image = smudge_image
smudged = vector_op(laptop_glow.node_tree.nodes, laptop_glow.node_tree.links, "MULTIPLY", smudge_texture.outputs["Color"], (0.03, 0.035, 0.04))
laptop_glow.node_tree.links.new(
	vector_op(laptop_glow.node_tree.nodes, laptop_glow.node_tree.links, "ADD", smudged, (0.035, 0.07, 0.1)),
	laptop_glow.node_tree.nodes["Principled BSDF"].inputs["Emission Color"],
)

# The screen is a plane with one UV square, so the site can draw post titles on it.
bpy.ops.mesh.primitive_plane_add(size=1, location=lid_center + lid_front * 0.025, rotation=radians((78, 0, 0)))
screen = bpy.context.object
screen.name = "laptop-screen"
screen.scale = (1.15, 0.72, 1)
finish(screen, laptop_glow)

# ---------------------------------------------------------------- mug, phone, plant

mug = cylinder("mug", (0.75, 0.25, DESK_Z + 0.18), 0.16, 0.36, glaze, vertices=64)
mug_inside = cylinder("mug-cutter", (0.75, 0.25, DESK_Z + 0.22), 0.135, 0.36, glaze, vertices=64)
cut(mug, mug_inside)
activate(mug)
bevel = mug.modifiers.new("rim", "BEVEL")
bevel.width = 0.012
bevel.segments = 3
bpy.ops.object.convert(target="MESH")
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
cylinder("mug-coffee", (0.75, 0.25, DESK_Z + 0.29), 0.136, 0.005, coffee, vertices=64)
torus("mug-handle", (0.93, 0.25, DESK_Z + 0.19), 0.085, 0.026, glaze, rotation=(90, 0, 0))

# The phone stands on a little stand, leaning back and turned towards the
# chair, so you can see what's playing. Its screen is a plane with one UV
# square, like the laptop's, for the live scene to draw on.
PHONE_BASE = Vector((1.55, 0.05, DESK_Z + 0.06))
phone_turn = Matrix.Rotation(math.radians(-16), 3, "Z") @ Matrix.Rotation(math.radians(-20), 3, "X")
phone_angles = tuple(math.degrees(a) for a in phone_turn.to_euler())
phone_up = phone_turn @ Vector((0, 0, 1))
phone_front = phone_turn @ Vector((0, -1, 0))
stand_plastic = material("phone-stand", (0.08, 0.08, 0.09), rough=0.5, photo="Plastic013A", photo_size=0.4, scratches=0.1, dirt=0.3)
flat_turn = (0, 0, -16)
facing = Matrix.Rotation(math.radians(-16), 3, "Z")
box("phone-stand-base", PHONE_BASE + facing @ Vector((0, 0.1, -0.05)), (0.3, 0.34, 0.02), stand_plastic, rotation=flat_turn, bevel=0.006)
box("phone-stand-lip", PHONE_BASE + facing @ Vector((0, -0.03, -0.025)), (0.3, 0.04, 0.05), stand_plastic, rotation=flat_turn, bevel=0.006)
box("phone-stand-back", PHONE_BASE + phone_turn @ Vector((0, 0.03, 0.22)), (0.18, 0.02, 0.42), stand_plastic, rotation=phone_angles, bevel=0.006)
box("phone", PHONE_BASE + phone_up * 0.36, (0.36, 0.035, 0.72), phone_body, rotation=phone_angles, bevel=0.03, segments=4)
bpy.ops.mesh.primitive_plane_add(size=1, location=PHONE_BASE + phone_up * 0.36 + phone_front * 0.0185)
phone_screen = bpy.context.object
phone_screen.name = "phone-screen"
phone_screen.rotation_euler = (phone_turn @ Matrix.Rotation(math.radians(90), 3, "X")).to_euler()
phone_screen.scale = (0.32, 0.66, 1)
finish(phone_screen, phone_glow)

# The plant: a hand-thrown terracotta pot, a little lumpy, with a rolled rim
# chipped on the side facing you, standing in a saucer. Profiles are
# (radius, height), up the outside and back down the inside.
PLANT = Vector((2.55, 0.75, DESK_Z))
SAUCER = [(0, 0), (0.195, 0), (0.2, 0.004), (0.226, 0.03), (0.23, 0.036), (0.224, 0.038), (0.214, 0.014), (0, 0.012)]
POT = [(0, 0), (0.148, 0), (0.152, 0.008), (0.178, 0.235), (0.18, 0.245), (0.197, 0.25), (0.2, 0.258), (0.2, 0.305), (0.195, 0.315), (0.18, 0.318), (0.17, 0.31), (0.166, 0.28)]
lathe("plant-saucer", PLANT, SAUCER, terracotta, wobble=0.015)
lathe("plant-pot", PLANT + Vector((0, 0, 0.012)), POT, terracotta, wobble=0.03, chip=-105)
cylinder("plant-soil", PLANT + Vector((0, 0, 0.302)), 0.168, 0.02, soil)
for i, (spin, lean, height) in enumerate([(0, 8, 0.36), (52, 16, 0.3), (105, 12, 0.33), (160, 20, 0.27), (210, 10, 0.34), (262, 18, 0.29), (315, 14, 0.31)]):
	angle = math.radians(spin)
	offset = Vector((math.cos(angle), math.sin(angle), 0)) * 0.06
	sphere(f"plant-leaf-{i}", PLANT + Vector((0, 0, 0.31 + height)) + offset, 1, leaf, scale=(0.055, 0.018, height), rotation=(lean, 0, spin + 90), segments=24)

# A notebook and pen on the left of the desk: the About page.
cover = material("notebook-cover", (0.12, 0.45, 0.48), rough=0.7, photo="Fabric061", photo_size=0.4, photo_bump=0.3, dirt=0.3)
box("notebook", (-2.35, 0.3, DESK_Z + 0.03), (0.72, 0.98, 0.06), cover, rotation=(0, 0, 9), bevel=0.015)
box("notebook-pages", (-2.35, 0.3, DESK_Z + 0.03), (0.69, 0.95, 0.045), material("pages", (0.8, 0.76, 0.66), rough=0.9, pattern=bands("Z", 220, 0.85, 1.05, wobble=0.5)), rotation=(0, 0, 9))
box("notebook-band", (-2.2, 0.32, DESK_Z + 0.03), (0.03, 1.0, 0.065), orange, rotation=(0, 0, 9))
cylinder("notebook-pen", (-1.75, 0.35, DESK_Z + 0.02), 0.018, 0.7, rib, rotation=(90, 0, 4), vertices=16)

# A desk lamp on the left: a warm pool of light on the notebook, and real shadows.
lamp_base = Vector((-4.05, 0.95, DESK_Z + 0.025))
lamp_elbow = Vector((-3.95, 1.25, 1.9))
lamp_head = Vector((-3.45, 0.75, 2.05))
lamp_target = Vector((-2.55, 0.35, DESK_Z))
cylinder("lamp-base", lamp_base, 0.17, 0.05, rib, bevel=0.01)
rod("lamp-arm-low", lamp_base, lamp_elbow, 0.022, steel)
rod("lamp-arm-high", lamp_elbow, lamp_head, 0.022, steel)
sphere("lamp-elbow", lamp_elbow, 0.04, rib, segments=16)
aim = (lamp_target - lamp_head).normalized()
bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=0.2, radius2=0.06, depth=0.26, location=lamp_head + aim * 0.05)
shade = bpy.context.object
shade.name = "lamp-shade"
shade.rotation_euler = (-aim).to_track_quat("Z", "Y").to_euler()
# Orange paint, chipped back to the steel at the rim.
finish(shade, worn_paint("lamp-paint", (0.7, 0.22, 0.06), (0.75, 0.75, 0.78), bare="Metal038", bare_size=0.4), 0.01, smooth=40)
bulb_at = lamp_head + aim * 0.19
sphere("lamp-bulb", bulb_at, 0.07, material("bulb", (0, 0, 0), emit=(1.0, 0.8, 0.55), strength=12), segments=16)

# Painted stencils and a vent on the walls.
stencil("stencil-deck", "DECK 2", (-4.675, -2.2, 3.7), (1, 0, 0), 0.45, orange)
stencil("stencil-o2", "O2", (4.675, -2.6, 3.75), (-1, 0, 0), 0.5, orange)
stencil("stencil-life", "LIFE SUPPORT", (4.675, -2.6, 3.35), (-1, 0, 0), 0.16, rib)
# In paint of its own, not the wall's, so the bake can give its letters more room (island_scale).
stencil_paint = material("stencil-cream", (0.86, 0.79, 0.67), rough=0.55, photo="PaintedMetal012", photo_size=2.7, photo_bump=0.25, grime=0.4, dirt=0.5)
stencil("stencil-viewport", "VIEWPORT 1", (1.5, 1.774, WINDOW["z"] - 1.12), (0, -1, 0), 0.075, stencil_paint)
box("vent-panel", (-4.68, -2.2, 2.55), (0.03, 0.9, 0.6), rib, bevel=0.01)
for i in range(7):
	box(f"vent-slat-{i}", (-4.66, -2.2, 2.33 + 0.072 * i), (0.03, 0.8, 0.03), charcoal, rotation=(30, 0, 0))

# A laminated Morse card beside the viewport: the key to the light outside.
# Letters and digits from src/data/morse.json, which the website's chart uses too.
with open(os.path.join(ROOT, "src", "data", "morse.json")) as file:
	MORSE = json.load(file)
card_center = Vector((-3.35, 1.993, 2.45))
laminate = material("laminate", (1.7, 1.65, 1.55), rough=0.2, photo="Paper006", photo_size=0.8, prints=0.2, dirt=0.25)
ink = material("ink", (0.04, 0.04, 0.05), rough=0.6)
box("morse-card", card_center, (0.56, 0.004, 0.74), laminate, bevel=0.01)
sphere("morse-pin", card_center + Vector((0, -0.012, 0.34)), 0.02, material("pin", (0.6, 0.05, 0.04), rough=0.3), segments=12)
stencil("morse-title", "MORSE", card_center + Vector((0, -0.003, 0.28)), (0, -1, 0), 0.075, ink)
columns = [list(MORSE)[0:13], list(MORSE)[13:26], list(MORSE)[26:36]]
for c, keys in enumerate(columns):
	for r, key in enumerate(keys):
		at = card_center + Vector((-0.25 + 0.18 * c, -0.003, 0.2 - 0.04 * r))
		stencil(f"morse-{key}", f"{key} {MORSE[key]}", at, (0, -1, 0), 0.03, ink, align="LEFT")

# ---------------------------------------------------------------- clutter

# Everything below is placed with a fixed random seed, so every build makes
# the same mess. All words here are rough drafts, to be rewritten.
random.seed(7)
caveat = font("caveat", "Caveat.ttf")
marker = font("permanent-marker", "PermanentMarker-Regular.ttf")
anton = font("anton", "Anton-Regular.ttf")
pen_ink = material("pen-ink", (0.03, 0.05, 0.16), rough=0.6)
marker_ink = material("marker-ink", (0.02, 0.02, 0.025), rough=0.7)


def paper(name, tint):
	return material(name, tint, rough=0.85, photo="Paper006", photo_size=0.35, dirt=0.2)


# Post-it notes stuck along the bottom of the window frame.
POSTITS = [
	(-2.2, (1.9, 1.7, 0.6), "backups!!", -5),
	(-1.45, (1.9, 1.0, 1.15), "buy coffee", 4),
	(-1.13, (1.25, 1.8, 0.95), "water\nthe plant", -3),
	(0.27, (1.0, 1.5, 1.9), "tune the\nG string", 6),
	(0.95, (1.9, 1.7, 0.6), "call home", -4),
	(2.12, (1.95, 1.3, 0.6), "fix the\ncrack ->", 3),
]
for i, (x, tint, words, spin) in enumerate(POSTITS):
	z = 1.86 + random.uniform(-0.02, 0.02)
	box(f"postit-{i}", (x, 1.776, z), (0.3, 0.004, 0.3), paper(f"postit-{i}", tint), rotation=(0, spin, 0))
	stencil(f"postit-{i}-words", words, (x, 1.772, z), (0, -1, 0), 0.07, pen_ink, typeface=caveat, spin=spin)


def cable(name, points, radius, mat, resolution=6):
	"""A cable along smooth curves through the given points."""
	curve = bpy.data.curves.new(name, "CURVE")
	curve.dimensions = "3D"
	curve.bevel_depth = radius
	curve.bevel_resolution = 2
	curve.resolution_u = resolution
	spline = curve.splines.new("BEZIER")
	spline.bezier_points.add(len(points) - 1)
	for point, co in zip(spline.bezier_points, points):
		point.co = co
		point.handle_left_type = point.handle_right_type = "AUTO"
	obj = bpy.data.objects.new(name, curve)
	scene.collection.objects.link(obj)
	activate(obj)
	bpy.ops.object.convert(target="MESH")
	return finish(obj, mat, smooth=60)


def wander(start, end, steps, jitter, radius):
	"""Points from start to end that drift about on the desk, lifting a little
	here and there as if crossing other cables."""
	start, end = Vector(start), Vector(end)
	points = [start]
	for i in range(1, steps):
		t = i / steps
		p = start.lerp(end, t)
		p.x += random.uniform(-jitter, jitter)
		p.y += random.uniform(-jitter, jitter)
		p.z = DESK_Z + radius + random.choice((0, 0, 0.012, 0.02))
		points.append(p)
	points.append(end)
	return points


black_cable = material("cable-black", (0.02, 0.02, 0.022), rough=0.5, dust=0.3, dirt=0.2)
white_cable = material("cable-white", (0.72, 0.72, 0.7), rough=0.4, grime=0.15, dust=0.2, dirt=0.2)
r = 0.012
# Laptop, phone and lamp all run back to the one overloaded wall socket (see
# "the outlet" below): along the back of the desk, then up to their plugs.
cable("cable-laptop", wander((-1.17, 0.5, DESK_Z + r), (-1.39, 1.41, DESK_Z + r), 7, 0.22, r), r, white_cable)
box("cable-charger", (-1.45, 1.55, DESK_Z + 0.045), (0.22, 0.3, 0.09), white_cable, rotation=(0, 0, 25), bevel=0.02)
cable("cable-laptop-mains", [Vector(p) for p in (
	(-1.52, 1.72, DESK_Z + r), (-1.4, 1.82, DESK_Z + r), (-0.8, 1.83, DESK_Z + r), (-0.2, 1.81, DESK_Z + r),
	(0.35, 1.82, DESK_Z + r), (0.7, 1.84, DESK_Z + r), (0.76, 1.79, 1.12), (0.745, 1.785, 1.18),
)], r, white_cable)
cable("cable-phone", [PHONE_BASE + Vector((0, -0.02, -0.02)), Vector((1.5, -0.08, DESK_Z + r))] + wander((1.4, -0.25, DESK_Z + r), (1.85, 1.95, DESK_Z + r), 8, 0.28, r) + [Vector(p) for p in (
	(1.5, 1.86, DESK_Z + r), (1.0, 1.78, DESK_Z + r), (0.85, 1.66, DESK_Z + r), (0.5, 1.64, DESK_Z + r),
	(0.32, 1.62, DESK_Z + r), (0.28, 1.56, 1.2), (0.3, 1.53, 1.245),
)], r, white_cable)
cable("cable-lamp", wander((-4.05, 0.95, DESK_Z + r), (-4.3, 1.95, DESK_Z + r), 4, 0.12, r) + [Vector(p) for p in (
	(-3.6, 1.95, DESK_Z + r), (-2.4, 1.95, DESK_Z + r), (-1.2, 1.95, DESK_Z + r), (0.0, 1.95, DESK_Z + r),
	(0.3, 1.9, DESK_Z + r), (0.37, 1.78, 1.15), (0.385, 1.735, 1.2),
)], r, black_cable)
# The headphones' lead hangs from the left cup, down the wall, and coils on the desk.
cup_low = Vector((-3.88, 1.82, 2.88))
cable("cable-headphones", [cup_low, Vector((-3.86, 1.9, 2.4)), Vector((-3.75, 1.95, 1.6)), Vector((-3.55, 1.7, DESK_Z + 0.01)),
	Vector((-3.1, 1.35, DESK_Z + 0.01)), Vector((-2.85, 1.65, DESK_Z + 0.018)), Vector((-3.2, 1.9, DESK_Z + 0.01)),
	Vector((-3.45, 1.45, DESK_Z + 0.02)), Vector((-3.0, 1.2, DESK_Z + 0.01))], 0.008, black_cable)
cable("cable-usb", wander((-2.9, 1.05, DESK_Z + r), (-0.95, 1.35, DESK_Z + r), 9, 0.25, r), 0.01, black_cable)
box("cable-usb-plug", (-0.95, 1.35, DESK_Z + 0.015), (0.08, 0.035, 0.03), steel, rotation=(0, 0, 15))

# ---------------------------------------------------------------- the outlet
# One double socket, dangerously overloaded. The left socket takes a cube
# adapter with another cube adapter in it, sagging, which takes the desk
# lamp and a power strip; the right a travel adapter for the laptop. The
# strip, on the desk, takes the phone charger, a third cube adapter, a
# second strip (daisy-chained) and a plug whose cable goes nowhere. The
# strip's plug has scorched, the plate is scorched round the travel adapter,
# and soot has crept up the wall to the right of the postcard.
ox, oz = OUTLET
outlet_plastic = material("outlet-plate", (0.8, 0.77, 0.66), rough=0.45, photo="Plastic013A", photo_size=0.3, grime=0.4, dirt=0.4, pattern=scorch(ox + 0.12, oz - 0.04, 0.12))
adapter_white = material("adapter-plastic", (0.78, 0.76, 0.68), rough=0.45, photo="Plastic013A", photo_size=0.3, grime=0.35, dirt=0.4, scratches=0.1)
plug_black = material("plug-black", (0.03, 0.03, 0.03), rough=0.4, photo="Plastic013A", photo_size=0.3, scratches=0.15, dirt=0.3)
scorched = material("scorched-plug", (0.1, 0.06, 0.035), rough=0.6, bump=0.3, bump_scale=120, dirt=0.5)
box("outlet-plate", (ox, 1.988, oz), (0.5, 0.024, 0.24), outlet_plastic, bevel=0.01)
box("outlet-adapter-a", (ox - 0.12, 1.891, oz), (0.17, 0.17, 0.17), adapter_white, bevel=0.012)
box("outlet-adapter-b", (ox - 0.12, 1.731, oz - 0.005), (0.15, 0.15, 0.15), adapter_white, rotation=(-6, 0, 3), bevel=0.012)
box("outlet-plug-lamp", (ox - 0.235, 1.731, oz), (0.08, 0.07, 0.09), plug_black, bevel=0.01)
box("outlet-plug-strip", (ox - 0.12, 1.62, oz - 0.015), (0.08, 0.075, 0.1), scorched, bevel=0.01)
box("outlet-travel-adapter", (ox + 0.12, 1.906, oz - 0.01), (0.15, 0.14, 0.17), adapter_white, bevel=0.012)
box("outlet-plug-laptop", (ox + 0.125, 1.786, oz - 0.02), (0.09, 0.1, 0.11), adapter_white, bevel=0.01)
# The first strip, on the desk under it all, its switch glowing.
strip_turn = math.radians(-6)
along = Vector((math.cos(strip_turn), math.sin(strip_turn), 0))
strip_at = Vector((ox - 0.12, 1.5, DESK_Z + 0.025))
box("outlet-strip", strip_at, (0.6, 0.11, 0.05), adapter_white, rotation=(0, 0, -6), bevel=0.01)
box("outlet-strip-switch", strip_at - along * 0.26 + Vector((0, 0, 0.03)), (0.05, 0.05, 0.015), material("strip-switch", (0, 0, 0), emit=(1.0, 0.12, 0.05), strength=3), rotation=(0, 0, -6))
sockets = [strip_at + along * offset + Vector((0, 0, 0.025)) for offset in (-0.17, -0.04, 0.09, 0.21)]
box("outlet-phone-charger", sockets[0] + Vector((0, 0, 0.05)), (0.08, 0.06, 0.1), adapter_white, rotation=(0, 0, -6), bevel=0.01)
box("outlet-adapter-c", sockets[1] + Vector((0, 0, 0.055)), (0.11, 0.11, 0.11), adapter_white, rotation=(0, 0, -6), bevel=0.01)
box("outlet-plug-c", sockets[1] + Vector((0, -0.08, 0.055)), (0.06, 0.05, 0.07), plug_black, rotation=(0, 0, -6), bevel=0.008)
box("outlet-plug-chain", sockets[2] + Vector((0, 0, 0.045)), (0.06, 0.06, 0.09), plug_black, rotation=(0, 0, -6), bevel=0.008)
box("outlet-plug-spare", sockets[3] + Vector((0, 0, 0.045)), (0.06, 0.06, 0.09), plug_black, rotation=(0, 0, -6), bevel=0.008)
# The second strip, chained off the first, to the right.
strip_two = Vector((1.0, 1.45, DESK_Z + 0.023))
box("outlet-strip-two", strip_two, (0.5, 0.1, 0.045), adapter_white, rotation=(0, 0, 20), bevel=0.01)
two_along = Vector((math.cos(math.radians(20)), math.sin(math.radians(20)), 0))
box("outlet-strip-two-charger", strip_two - two_along * 0.12 + Vector((0, 0, 0.07)), (0.07, 0.05, 0.09), adapter_white, rotation=(0, 0, 20), bevel=0.01)
cable("cable-strip", [Vector(p) for p in ((strip_at + along * 0.31).to_tuple(), (0.95, 1.6, DESK_Z + r), (0.7, 1.68, DESK_Z + 0.04), (0.52, 1.63, 1.15), (ox - 0.12, 1.62, oz - 0.06))], r, white_cable)
cable("cable-chain", [Vector(p) for p in ((sockets[2] + Vector((0, 0.03, 0.07))).to_tuple(), (0.6, 1.6, DESK_Z + r), (0.72, 1.58, DESK_Z + r), (strip_two - two_along * 0.25).to_tuple())], 0.01, black_cable)
cable("cable-adapter-c", [Vector(p) for p in ((sockets[1] + Vector((0, -0.1, 0.03))).to_tuple(), (0.4, 1.32, DESK_Z + r), (0.25, 1.2, DESK_Z + r), (0.32, 1.05, DESK_Z + r), (0.5, 1.1, DESK_Z + r), (0.46, 1.24, DESK_Z + r))], 0.01, black_cable)
cable("cable-spare", [Vector(p) for p in ((sockets[3] + Vector((0, 0.03, 0.07))).to_tuple(), (0.75, 1.62, DESK_Z + r), (0.62, 1.75, DESK_Z + r), (0.58, 1.9, DESK_Z + r), (0.85, 1.93, DESK_Z + r))], 0.01, black_cable)
cable("cable-strip-two-charger", [Vector(p) for p in ((strip_two - two_along * 0.12 + Vector((0, 0, 0.115))).to_tuple(), (0.9, 1.3, DESK_Z + r), (1.05, 1.32, DESK_Z + r), (1.3, 1.45, DESK_Z + r), (1.35, 1.62, DESK_Z + r), (1.2, 1.7, DESK_Z + r))], 0.01, white_cable)

# Old backup discs: a stack of jewel cases, and one disc out of its case.
case_tray = material("case-tray", (0.03, 0.03, 0.035), rough=0.3, photo="Plastic013A", photo_size=0.4, scratches=0.15)
case_cover = material("case-cover", (0.5, 0.52, 0.55), rough=0.08, photo="Plastic013A", photo_size=0.4, scratches=0.25, prints=0.35)
insert = paper("disc-insert", (1.7, 1.7, 1.65))
LABELS = ["BACKUP\n2009", "PHOTOS\n2011", "DO NOT\nLOSE"]
# What floats with each case besides its tray, lid and insert (FLOATERS).
DISC_PARTS = {0: ["disc-strip-0", "disc-spine-0", "disc-sticker", "disc-password"], 1: ["disc-strip-1", "disc-spine-1"], 2: ["disc-label"]}
cases = []
# Each case is a tray and a lid stacked flush, with its paper insert flat on
# top. Nothing is much thinner than a centimetre: from the desk chair, thinner
# layers and the gaps between them are a pixel high and shimmer as you move.
for i in range(3):
	at = Vector((-1.78 + random.uniform(-0.04, 0.04), 1.28 + random.uniform(-0.04, 0.04), DESK_Z + 0.03 * i))
	turn = random.uniform(-14, 14)
	box(f"disc-case-{i}", at + Vector((0, 0, 0.01)), (0.48, 0.42, 0.02), case_tray, rotation=(0, 0, turn))
	box(f"disc-cover-{i}", at + Vector((0, 0, 0.025)), (0.48, 0.42, 0.01), case_cover, rotation=(0, 0, turn))
	bpy.ops.mesh.primitive_plane_add(size=1, location=at + Vector((0, 0, 0.0305)), rotation=(0, 0, math.radians(turn)))
	sheet = bpy.context.object
	sheet.name = f"disc-insert-{i}"
	sheet.scale = (0.44, 0.38, 1)
	finish(sheet, insert)
	cases.append((at, turn))
top = Vector((-1.78, 1.28, DESK_Z + 0.03 * 3 + 0.001))
stencil("disc-label", LABELS[0], top, (0, 0, 1), 0.075, marker_ink, typeface=marker, spin=random.uniform(-8, 8))
# The two cases under it are named on paper strips along their front
# spines, as jewel cases are: the cases are black, and so is the marker.
for i in (0, 1):
	at, turn = cases[i]
	facing = Matrix.Rotation(math.radians(turn), 3, "Z")
	bpy.ops.mesh.primitive_plane_add(size=1, location=at + facing @ Vector((0, -0.2103, 0.015)), rotation=(math.pi / 2, 0, math.radians(turn)))
	strip = bpy.context.object
	strip.name = f"disc-strip-{i}"
	strip.scale = (0.4, 0.024, 1)
	finish(strip, insert)
	stencil(f"disc-spine-{i}", LABELS[2 - i].replace("\n", " "), at + facing @ Vector((0, -0.2106, 0.015)), facing @ Vector((0, -1, 0)), 0.016, marker_ink, typeface=marker)
# The backup's password, on a sticker under DO NOT LOSE: it faces the desk,
# so it's only seen once the case floats and turns over (cabin.js). The
# sticker only glows, faintly: lit, the bake would leave it as dark as the
# desk it faces, with shadows on it.
at, turn = cases[0]
bpy.ops.mesh.primitive_plane_add(size=1, location=at + Vector((0, 0, -0.0008)), rotation=(math.pi, 0, 0))
sticker = bpy.context.object
sticker.name = "disc-sticker"
sticker.scale = (0.36, 0.14, 1)
finish(sticker, material("disc-sticker", (0, 0, 0), rough=0.85, emit=(0.34, 0.33, 0.3)))
password = stencil("disc-password", "backup password:\nflexbox", at + Vector((0, 0, -0.0016)), (0, 0, -1), 0.032, marker_ink, typeface=marker)
with_case = Matrix.Translation(at) @ Matrix.Rotation(math.radians(turn), 4, "Z") @ Matrix.Translation(-at)
for obj in (sticker, password):
	obj.matrix_world = with_case @ obj.matrix_world
foil = material("disc-foil", (0.8, 0.8, 0.82), rough=0.12, metal=1.0)
# A thin film gives the rainbow sheen of a recordable disc.
if "Thin Film Thickness" in foil.node_tree.nodes["Principled BSDF"].inputs:
	foil.node_tree.nodes["Principled BSDF"].inputs["Thin Film Thickness"].default_value = 550
loose = cylinder("disc-loose", (-2.45, 1.55, DESK_Z + 0.004), 0.24, 0.006, foil, vertices=96)
cut(loose, cylinder("disc-hole", (-2.45, 1.55, DESK_Z + 0.004), 0.03, 0.05, foil))
# The hub is flat, with no sides a millimetre high.
bpy.ops.mesh.primitive_circle_add(vertices=64, radius=0.075, fill_type="NGON", location=(-2.45, 1.55, DESK_Z + 0.0075))
hub = bpy.context.object
hub.name = "disc-hub"
finish(hub, material("disc-hub", (0.6, 0.62, 0.65), rough=0.3))
stencil("disc-loose-label", "BACKUP 09", (-2.45, 1.40, DESK_Z + 0.0095), (0, 0, 1), 0.045, marker_ink, typeface=marker, spin=12)

# A stack of books under the lamp, spines turned to the chair. Each is two
# boards and a spine round a block of pages. They have their own random, so
# the rest of the clutter lands where it always has.
book_ink = {"dark": material("book-ink-dark", (0.02, 0.02, 0.025), rough=0.6), "light": material("book-ink-light", (0.85, 0.8, 0.68), rough=0.6)}
BOOKS = [
	# title, (length, depth, thickness), cover colour, ink, lettering size
	("Javascript for space sickness", (0.72, 0.5, 0.11), (0.8, 0.62, 0.08), "dark", 0.046),
	("CSS2001: a spacing odyssey", (0.66, 0.46, 0.085), (0.42, 0.09, 0.05), "light", 0.042),
	("Node.JS relativity", (0.6, 0.42, 0.075), (0.16, 0.36, 0.14), "light", 0.04),
]
shelf = random.Random(2001)
stack_at = Vector((-3.35, 0.78, DESK_Z))
for i, (title, (length, depth, thick), colour, ink, size) in enumerate(BOOKS):
	turn = 22 + shelf.uniform(-5, 5)
	facing = Matrix.Rotation(math.radians(turn), 3, "Z")
	at = stack_at + Vector((shelf.uniform(-0.03, 0.03), shelf.uniform(-0.03, 0.03), thick / 2))
	stack_at.z += thick
	board = 0.012
	cloth = material(f"book-cover-{i}", colour, rough=0.75, photo="Fabric061", photo_size=0.4, photo_bump=0.2, dirt=0.3)
	for part, centre, dims, mat in (
		("bottom", (0, board / 2, -thick / 2 + board / 2), (length, depth - board, board), cloth),
		("top", (0, board / 2, thick / 2 - board / 2), (length, depth - board, board), cloth),
		("spine", (0, -depth / 2 + board / 2, 0), (length, board, thick), cloth),
		("pages", (0, 0, 0), (length - 0.024, depth - board - 0.012, thick - 2 * board), bpy.data.materials["pages"]),
	):
		box(f"book-{i}-{part}", at + facing @ Vector(centre), dims, mat, rotation=(0, 0, turn), bevel=0.004)
	words = stencil(f"book-{i}-title", title, at + facing @ Vector((0, -depth / 2 - 0.0005, 0)), facing @ Vector((0, -1, 0)), size, book_ink[ink], typeface=anton)
	assert words.dimensions.x < length - 0.06, f"{title!r} is too long for its spine"

# Hand sanitiser.
gel = material("sanitiser-gel", (0.55, 0.8, 0.85), rough=0.15, photo="Plastic013A", photo_size=0.4, prints=0.25)
pump_white = material("sanitiser-pump", (1.2, 1.2, 1.2), rough=0.35, photo="Plastic013A", photo_size=0.4, dirt=0.2)
bottle = Vector((2.1, 1.35, DESK_Z))
cylinder("sanitiser-bottle", bottle + Vector((0, 0, 0.19)), 0.085, 0.38, gel, bevel=0.02)
cylinder("sanitiser-label", bottle + Vector((0, 0, 0.17)), 0.087, 0.15, paper("sanitiser-paper", (1.8, 1.8, 1.75)))
stencil("sanitiser-words", "HAND\nSANITISER", bottle + Vector((0, -0.089, 0.17)), (0, -1, 0), 0.035, material("label-ink", (0.0, 0.25, 0.45), rough=0.6), typeface=anton)
cylinder("sanitiser-neck", bottle + Vector((0, 0, 0.405)), 0.035, 0.05, pump_white)
cylinder("sanitiser-pump", bottle + Vector((0, 0, 0.45)), 0.022, 0.05, pump_white)
box("sanitiser-nozzle", bottle + Vector((0, -0.04, 0.475)), (0.045, 0.11, 0.035), pump_white, bevel=0.01)


def web(center, radius):
	"""Pattern: a black spider's web printed on a cup, centred on the side that
	faces the camera. Built from the angle around the cup's axis and the
	height, unrolled flat."""
	def build(nodes, links, colour, position):
		local = vector_op(nodes, links, "SUBTRACT", position, tuple(center))
		parts = nodes.new("ShaderNodeSeparateXYZ")
		links.new(local, parts.inputs[0])
		around = math_node(nodes, links, "ARCTAN2", parts.outputs["Y"], parts.outputs["X"])
		u = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "ADD", around, math.pi / 2), radius)
		v = parts.outputs["Z"]
		reach = math_node(nodes, links, "SQRT", math_node(nodes, links, "ADD", math_node(nodes, links, "MULTIPLY", u, u), math_node(nodes, links, "MULTIPLY", v, v)))
		bearing = math_node(nodes, links, "ARCTAN2", v, u)
		spokes = math_node(nodes, links, "LESS_THAN", math_node(nodes, links, "ABSOLUTE", math_node(nodes, links, "SINE", math_node(nodes, links, "MULTIPLY", bearing, 4))), math_node(nodes, links, "DIVIDE", 0.006, math_node(nodes, links, "ADD", reach, 0.001)))
		rings = math_node(nodes, links, "GREATER_THAN", math_node(nodes, links, "ABSOLUTE", math_node(nodes, links, "SUBTRACT", math_node(nodes, links, "FRACT", math_node(nodes, links, "DIVIDE", reach, 0.035)), 0.5)), 0.43)
		inside = math_node(nodes, links, "LESS_THAN", reach, 0.15)
		lines = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "MAXIMUM", spokes, rings), inside)
		return mix_colour(nodes, links, lines, colour, (0.02, 0.02, 0.02))
	return build


# A cup of pens, with a spider's web printed on it.
cup_at = Vector((1.18, 1.15, DESK_Z))
cup_glaze = material("cup-glaze", (0.55, 0.04, 0.03), rough=0.3, bump=0.02, bump_scale=200, dirt=0.25, pattern=web(cup_at + Vector((0, 0, 0.2)), 0.13))
cup = cylinder("cup-body", cup_at + Vector((0, 0, 0.18)), 0.13, 0.36, cup_glaze, vertices=64)
cut(cup, cylinder("cup-hollow", cup_at + Vector((0, 0, 0.22)), 0.11, 0.36, cup_glaze, vertices=64))
PENS = [
	((-0.04, 0.03), 0.62, (6, -4), (0.05, 0.1, 0.5)),
	((0.04, 0.04), 0.58, (-5, -7), (0.02, 0.02, 0.02)),
	((0.0, -0.05), 0.6, (2, 8), (0.6, 0.05, 0.04)),
	((0.06, -0.02), 0.55, (-9, 3), (0.05, 0.1, 0.5)),
	((-0.06, -0.03), 0.57, (10, 6), (0.02, 0.02, 0.02)),
]
for i, ((dx, dy), length, (lean_x, lean_y), body) in enumerate(PENS):
	base = cup_at + Vector((dx, dy, 0.05))
	tip = base + Vector((math.sin(math.radians(lean_x)), math.sin(math.radians(lean_y)), 1)).normalized() * length
	rod(f"cup-pen-{i}", base, tip, 0.012, material(f"pen-{i}", body, rough=0.35))
	rod(f"cup-pen-{i}-cap", tip - (tip - base).normalized() * 0.09, tip, 0.014, material(f"pen-cap-{i}", body, rough=0.3))
pencil_tip = cup_at + Vector((-0.02, 0.0, 0.05)) + Vector((-0.12, 0.05, 1)).normalized() * 0.68
rod("cup-pencil", cup_at + Vector((-0.02, 0.0, 0.05)), pencil_tip, 0.015, material("pencil", (0.85, 0.6, 0.08), rough=0.6), vertices=6)
rod("cup-pencil-eraser", pencil_tip - Vector((-0.12, 0.05, 1)).normalized() * 0.04, pencil_tip, 0.015, material("eraser", (0.85, 0.4, 0.45), rough=0.8), vertices=12)
marker_tip = cup_at + Vector((0.03, 0.01, 0.05)) + Vector((0.1, -0.04, 1)).normalized() * 0.6
rod("cup-marker", cup_at + Vector((0.03, 0.01, 0.05)), marker_tip, 0.025, marker_ink)
rod("cup-marker-band", marker_tip - Vector((0.1, -0.04, 1)).normalized() * 0.2, marker_tip - Vector((0.1, -0.04, 1)).normalized() * 0.16, 0.026, material("marker-band", (0.85, 0.85, 0.82), rough=0.4))

# Coffee rings on the desk mat, from mugs gone by.
stain = material("coffee-stain", (0.06, 0.035, 0.02), rough=0.6)
for i, (x, y) in enumerate(((0.35, 0.55), (0.55, 0.42))):
	ring = cylinder(f"stain-{i}", (x, y, DESK_Z + 0.0006), 0.165, 0.001, stain, vertices=64)
	cut(ring, cylinder(f"stain-{i}-hole", (x, y, DESK_Z + 0.0006), 0.15, 0.01, stain, vertices=64))

# A digestive biscuit with a bite out of it, beside the mug; its crumbs are
# in the desk mat's pattern.
biscuit_at = Vector((1.15, -0.05, DESK_Z + 0.0125))
biscuit_bake = material("biscuit", (0.62, 0.4, 0.18), rough=0.9, bump=0.4, bump_scale=90, dirt=0.3, pattern=speckle(60, 0.1, (0.36, 0.22, 0.09)))
biscuit = cylinder("biscuit", biscuit_at, 0.12, 0.025, biscuit_bake, bevel=0.006)
for i, (angle, size) in enumerate(((-20, 0.065), (15, 0.055))):
	toward = Vector((math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0))
	cut(biscuit, sphere(f"biscuit-bite-{i}", biscuit_at + toward * 0.13, size, biscuit_bake))

# A guitar plectrum: a rounded triangle of orange plastic, lying flat under
# the mug, with just its tip showing in front. It floats free when the
# gravity's off.
outline = smooth_loop([(0, -0.058), (0.03, -0.02), (0.05, 0.02), (0.035, 0.042), (0, 0.047), (-0.035, 0.042), (-0.05, 0.02), (-0.03, -0.02)], per_segment=6)
mesh = bmesh.new()
face = mesh.faces.new([mesh.verts.new((p.x, p.y, 0)) for p in outline])
bmesh.ops.translate(mesh, vec=(0, 0, 0.004), verts=[v for v in bmesh.ops.extrude_face_region(mesh, geom=[face])["geom"] if isinstance(v, bmesh.types.BMVert)])
bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
data = bpy.data.meshes.new("pick")
mesh.to_mesh(data)
mesh.free()
pick = bpy.data.objects.new("pick", data)
scene.collection.objects.link(pick)
pick.location = (0.773, 0.122, DESK_Z + 0.0015)
pick.rotation_euler = radians((0, 0, 10))
finish(pick, material("pick", (0.9, 0.36, 0.05), rough=0.55, grain=0.08, grain_scale=60, scratches=0.15))

# A receipt, screwed up into a ball. Its own random numbers, so the rest of
# the scene's stay as they were.
crumple = random.Random(5)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.065, location=(-1.45, -0.25, DESK_Z + 0.065))
ball = bpy.context.object
ball.name = "paper-ball"
for vertex in ball.data.vertices:
	vertex.co *= 1 + noise.noise(vertex.co * 30) * 0.28 + crumple.uniform(-0.06, 0.06)
finish(ball, paper("receipt", (1.6, 1.58, 1.5)))

# A postcard of a beach, sun-faded, taped to the wall just under the post-its
# that say "tune the G string" and "call home". Painted here: sky, sun, sea,
# surf, sand and a palm, inside a white border.
CARD_PIXELS = (512, 352)
width, height = CARD_PIXELS
U, V = np.meshgrid((np.arange(width) + 0.5) / width, (np.arange(height) + 0.5) / height)
card = np.zeros((height, width, 3), np.float32)
horizon, shore = 0.5, 0.3
surf = shore + 0.015 * np.sin(U * 26) + 0.008 * np.sin(U * 61 + 1)
sky = np.clip((V - horizon) / (1 - horizon), 0, 1)[:, :, None]
card[:] = (0.92, 0.82, 0.62) * (1 - sky) + np.array((0.36, 0.6, 0.86)) * sky
sun = np.exp(-((U - 0.7) ** 2 + ((V - 0.68) * 0.7) ** 2) / 0.06 ** 2)[:, :, None]
card = card * (1 - sun) + np.array((1.0, 0.93, 0.66)) * sun
sea = ((V < horizon) & (V > surf))[:, :, None]
depth = np.clip((V - surf) / (horizon - surf), 0, 1)[:, :, None]
waves = 0.06 * np.sin(V * 140 + np.sin(U * 9) * 3)[:, :, None]
card = np.where(sea, np.array((0.2, 0.62, 0.66)) * (1 - depth) + np.array((0.08, 0.32, 0.55)) * depth + waves, card)
foam = (np.abs(V - surf) < 0.012)[:, :, None]
card = np.where(foam, np.array((0.95, 0.97, 0.95)), card)
sand = (V <= surf - 0.012)[:, :, None]
card = np.where(sand, np.array((0.9, 0.78, 0.55)) * (0.94 + 0.06 * smooth_noise(U.shape, 90, np.random.default_rng(11)))[:, :, None], card)
# The palm: a leaning trunk and drooping fronds, in silhouette.
palm = np.zeros(U.shape, np.float32)
def stroke(points, thickness):
	for (ax, ay), (bx, by) in zip(points, points[1:]):
		dx, dy = bx - ax, by - ay
		along_line = np.clip(((U - ax) * dx + (V - ay) * dy * 0.69 ** 2) / (dx * dx + (dy * 0.69) ** 2), 0, 1)
		distance = np.hypot(U - ax - along_line * dx, (V - ay - along_line * dy) * 0.69)
		np.maximum(palm, np.clip((thickness - distance) / 0.004, 0, 1), out=palm)
top = (0.3, 0.86)
stroke([(0.18, 0.12), (0.22, 0.4), (0.26, 0.66), top], 0.012)
for tip in ((0.08, 0.7), (0.14, 0.8), (0.42, 0.78), (0.47, 0.66), (0.2, 0.93), (0.38, 0.94)):
	middle = ((top[0] + tip[0]) / 2, max(top[1], tip[1]) + 0.04)
	stroke([top, middle, tip], 0.007)
card = card * (1 - palm[:, :, None]) + np.array((0.12, 0.16, 0.1)) * palm[:, :, None]
# Faded by the sun, and a white border.
card = card * 0.8 + np.array((0.85, 0.8, 0.68)) * 0.2
border = (U < 0.05) | (U > 0.95) | (V < 0.07) | (V > 0.93)
card[border] = (0.9, 0.88, 0.82)
pixels = np.ones((height, width, 4), np.float32)
pixels[:, :, :3] = np.clip(card, 0, 1)
picture = bpy.data.images.new("postcard", width, height)
picture.pixels.foreach_set(pixels.ravel())
postcard_path = os.path.join(ROOT, "scene", "postcard.png")
picture.filepath_raw = postcard_path
picture.file_format = "PNG"
picture.save()
bpy.data.images.remove(picture)
postcard = material("postcard", (1, 1, 1), rough=0.45, dirt=0.2)
card_texture = postcard.node_tree.nodes.new("ShaderNodeTexImage")
card_texture.image = bpy.data.images.load(postcard_path)
postcard.node_tree.links.new(card_texture.outputs["Color"], postcard.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
card_at = Vector((OUTLET[0], 1.994, 1.56))
bpy.ops.mesh.primitive_plane_add(size=1, location=card_at, rotation=radians((90, 4, 0)))
card_plane = bpy.context.object
card_plane.name = "postcard"
card_plane.scale = (0.48, 0.33, 1)
finish(card_plane, postcard)

# A gig poster for a band that never was, between the rib and the guitar.
poster_at = Vector((3.32, 1.993, 3.22))
poster_ink_cream = material("poster-cream", (0.95, 0.88, 0.7), rough=0.8, grime=0.2)
poster_ink_red = material("poster-red", (0.7, 0.06, 0.04), rough=0.8, grime=0.2)
box("poster-sheet", poster_at, (0.62, 0.003, 0.92), paper("poster-paper", (0.16, 0.15, 0.14)), rotation=(0, 2, 0))
stencil("poster-band", "RINGS N'\nROSES", poster_at + Vector((0, -0.003, 0.3)), (0, -1, 0), 0.12, poster_ink_cream, typeface=anton, spin=2)
# The small print has inks of its own, so the bake can give it more room (island_scale).
stencil("poster-venue", "LIVE AT THE\nCASSINI DIVISION", poster_at + Vector((0, -0.003, -0.31)), (0, -1, 0), 0.045, material("poster-venue", (0.7, 0.06, 0.04), rough=0.8, grime=0.2), typeface=anton, spin=2)
stencil("poster-small", "ONE NIGHT ONLY  *  NO ATMOSPHERE", poster_at + Vector((0, -0.003, -0.41)), (0, -1, 0), 0.022, material("poster-small", (0.95, 0.88, 0.7), rough=0.8, grime=0.2), typeface=anton, spin=2)
# The emblem: a rose drawn as a rose curve (r = cos 5t), inside a planet's ring.
emblem = poster_at + Vector((0, -0.0035, -0.02))
petals = [Vector((0.15 * math.cos(5 * t) * math.cos(t), 0, 0.15 * math.cos(5 * t) * math.sin(t))) for t in (math.pi * i / 120 for i in range(241))]
cable("poster-rose", [emblem + p for p in petals], 0.004, poster_ink_red, resolution=1)
ring_points = [Vector((0.24 * math.cos(t), 0, 0.07 * math.sin(t))) for t in (2 * math.pi * i / 48 for i in range(49))]
cable("poster-ring", [emblem + Matrix.Rotation(math.radians(-18), 3, "Y") @ p for p in ring_points], 0.006, poster_ink_cream, resolution=2)
tape = material("tape", (0.75, 0.7, 0.55), rough=0.5, grime=0.3)
for i, (dx, dz) in enumerate(((-0.29, 0.44), (0.29, 0.44), (-0.29, -0.44), (0.29, -0.44))):
	box(f"poster-tape-{i}", poster_at + Vector((dx, -0.004, dz)), (0.12, 0.002, 0.04), tape, rotation=(0, 45 if dx * dz > 0 else -45, 0))
for i, dx in enumerate((-0.21, 0.21)):
	box(f"postcard-tape-{i}", card_at + Vector((dx, -0.003, 0.15)), (0.1, 0.002, 0.035), tape, rotation=(0, 40 if dx > 0 else -40, 0))

# A bare bulb on its cord, hanging left of the window. It's kept as its own
# object so the live scene can make it flicker.
BULB = Vector((-2.1, 0.2, 3.45))
cable("bulb-cord", [Vector((-2.1, 0.24, 4.95)), Vector((-2.12, 0.21, 4.2)), BULB + Vector((0, 0, 0.17))], 0.012, material("cord", (0.02, 0.02, 0.022), rough=0.6), resolution=4)
cylinder("bulb-socket", BULB + Vector((0, 0, 0.12)), 0.035, 0.09, steel, bevel=0.005, vertices=24)
bulb = sphere("bulb", BULB, 0.085, material("bulb-glow", (0, 0, 0), emit=(1.0, 0.52, 0.2), strength=4), scale=(1, 1, 1.18), segments=32)

# The window glass: a fine crack running in from the lower right, and faint
# smudges all over. Both are painted into one picture rather than modelled: a
# strip of geometry a few millimetres wide shimmers as the live camera moves,
# where a picture is smoothed at every distance. The glass is a little bigger
# than the opening, so its edges are buried in the frame.
GLASS_Y = 1.95
GLASS_SIZE = (WINDOW["width"] + 0.1, WINDOW["height"] + 0.1)
GLASS_PIXELS = (2048, 910)
crack_paint = np.zeros(GLASS_PIXELS[::-1], np.float32)
# Its own random numbers, so the rest of the scene's stay as they were.
crack_glints = np.random.default_rng(9)


def glass_pixel(point):
	return ((point.x / GLASS_SIZE[0] + 0.5) * GLASS_PIXELS[0], ((point.z - WINDOW["z"]) / GLASS_SIZE[1] + 0.5) * GLASS_PIXELS[1])


def crack_line(start, heading, length, width):
	"""Paints one wandering line of the crack into crack_paint, narrowing as it
	goes, and returns its points."""
	points = [Vector(start)]
	angle = heading
	while length > 0:
		step = random.uniform(0.04, 0.09)
		angle += random.uniform(-0.25, 0.25)
		points.append(points[-1] + Vector((math.cos(angle) * step, 0, math.sin(angle) * step)))
		length -= step
	for i, (a, b) in enumerate(zip(points, points[1:])):
		thickness = width * (1 - i / len(points)) * GLASS_PIXELS[0] / GLASS_SIZE[0]
		(ax, ay), (bx, by) = glass_pixel(a), glass_pixel(b)
		x0, x1 = max(0, int(min(ax, bx)) - 3), min(GLASS_PIXELS[0], int(max(ax, bx)) + 4)
		y0, y1 = max(0, int(min(ay, by)) - 3), min(GLASS_PIXELS[1], int(max(ay, by)) + 4)
		x = np.arange(x0, x1)[None, :] + 0.5
		y = np.arange(y0, y1)[:, None] + 0.5
		dx, dy = bx - ax, by - ay
		along = np.clip(((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy), 0, 1)
		distance = np.hypot(x - ax - along * dx, y - ay - along * dy)
		# Smooth-edged; a line thinner than a pixel is drawn a pixel wide but fainter.
		cover = np.clip(max(thickness, 1) / 2 + 0.5 - distance, 0, 1) * min(thickness, 1) * crack_glints.uniform(0.35, 1)
		np.maximum(crack_paint[y0:y1, x0:x1], cover, out=crack_paint[y0:y1, x0:x1])
	return points


main = crack_line((1.85, 0, 2.22), math.radians(150), 1.5, 0.005)
for at in main[3::4][:4]:
	crack_line(at, math.radians(random.choice((100, 200, 230, 130))), random.uniform(0.2, 0.45), 0.0035)

width, height = GLASS_PIXELS
smudges = photo_image("Smear004", "Color").copy()
smudges.scale(width, height)
smear = np.empty(width * height * 4, np.float32)
smudges.pixels.foreach_get(smear)
bpy.data.images.remove(smudges)
# The photo is stored as sRGB; as linear light, it's what the old shader read.
smear = smear.reshape(height, width, 4)[:, :, 0] ** 2.2


# Frost creeping in from the corners of the cold glass, and a thin rim of it
# along the edges, kept clear of the light in the window near the top.
frosty = np.random.default_rng(4)
X, Z = np.meshgrid(((np.arange(width) + 0.5) / width - 0.5) * GLASS_SIZE[0], ((np.arange(height) + 0.5) / height - 0.5) * GLASS_SIZE[1])
straight_x, straight_z, corner_radius = WINDOW["width"] / 2 - WINDOW["radius"], WINDOW["height"] / 2 - WINDOW["radius"], WINDOW["radius"]
qx, qz = np.abs(X) - straight_x, np.abs(Z) - straight_z
# How far in from the edge of the opening each point is, in metres.
inside = corner_radius - np.hypot(np.maximum(qx, 0), np.maximum(qz, 0)) - np.minimum(np.maximum(qx, qz), 0)
# Thickest in the middle of each rounded corner, thinning fast along the edges.
diagonal = corner_radius * (1 - 0.5 ** 0.5)
corner = np.exp(-((qx - diagonal) ** 2 + (qz - diagonal) ** 2) / 0.35 ** 2)
grain = sum(smooth_noise(X.shape, cells, frosty) * weight for cells, weight in ((6, 0.5), (14, 0.25), (32, 0.13), (80, 0.07), (200, 0.05)))
feathers = smooth_noise(X.shape, 260, frosty)
frost = np.clip(((0.02 + 0.15 * corner) * (0.5 + grain) - inside) / 0.04, 0, 1) * (0.75 + 0.25 * feathers)
pixels = np.empty((height, width, 4), np.float32)
pixels[:, :, :3] = (0.8, 0.82, 0.85) + frost[:, :, None] * (np.array((0.92, 0.95, 1.0)) - (0.8, 0.82, 0.85))
pixels[:, :, 3] = np.maximum.reduce([crack_paint * 0.4, smear * 0.15, frost * 0.35])
picture = bpy.data.images.new("glass-picture", width, height, alpha=True)
picture.pixels.foreach_set(pixels.ravel())
glass_path = os.path.join(ROOT, "scene", "glass.png")
picture.filepath_raw = glass_path
picture.file_format = "PNG"
picture.save()
bpy.data.images.remove(picture)


def overlay(name, path, strength=1.0, additive=False):
	"""A see-through picture over the room: glass, which hides a little of what's
	behind it, or haze (additive), which only adds light. Cycles draws it as
	emission, unlit, the way the live scene draws it. Returns that material and
	a plain one for the export, which the glTF exporter understands."""
	image = bpy.data.images.load(path)
	mat = bpy.data.materials.new(name)
	nodes, links = mat.node_tree.nodes, mat.node_tree.links
	nodes.remove(nodes["Principled BSDF"])
	texture = nodes.new("ShaderNodeTexImage")
	texture.image = image
	# Not repeated: each edge would blend into the opposite one, drawing a line.
	texture.extension = "EXTEND"
	emission = nodes.new("ShaderNodeEmission")
	links.new(texture.outputs["Color"], emission.inputs["Color"])
	clear = nodes.new("ShaderNodeBsdfTransparent")
	if additive:
		links.new(math_node(nodes, links, "MULTIPLY", texture.outputs["Alpha"], strength), emission.inputs["Strength"])
		mix = nodes.new("ShaderNodeAddShader")
		links.new(clear.outputs[0], mix.inputs[0])
		links.new(emission.outputs[0], mix.inputs[1])
	else:
		emission.inputs["Strength"].default_value = strength
		mix = nodes.new("ShaderNodeMixShader")
		links.new(texture.outputs["Alpha"], mix.inputs[0])
		links.new(clear.outputs[0], mix.inputs[1])
		links.new(emission.outputs[0], mix.inputs[2])
	links.new(mix.outputs[0], nodes["Material Output"].inputs["Surface"])
	export = bpy.data.materials.new(f"{name}-export")
	texture = export.node_tree.nodes.new("ShaderNodeTexImage")
	texture.image = image
	texture.extension = "EXTEND"
	bsdf = export.node_tree.nodes["Principled BSDF"]
	export.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
	export.node_tree.links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
	return mat, export


bpy.ops.mesh.primitive_plane_add(size=1, location=(0, GLASS_Y, WINDOW["z"]), rotation=radians((90, 0, 0)))
glass = bpy.context.object
glass.name = "glass"
glass.scale = (*GLASS_SIZE, 1)
# Cycles mixes it in in linear light, where it shows more than the live
# scene's blending does, so it glows a little less here to match.
glass_material, glass_export = overlay("glass", glass_path, strength=0.6)
glass.data.materials.append(glass_material)

# Haze under the ceiling: smoke and dust that's drifted up and caught the
# light. Three soft sheets across the room at different depths, so it shifts
# as the camera moves. Each is a picture painted here: drifting clouds,
# thicker towards the ceiling, brighter near the bulb and the ceiling panel,
# and fading out before the side walls. The live scene draws them the same
# way, at HAZE_STRENGTH, and lets them breathe.
HAZE_STRENGTH = 0.25
HAZE_PIXELS = (512, 128)
haze_sheets = []
for i, (y, bottom) in enumerate(((1.4, 3.0), (0.1, 2.8), (-1.4, 2.6))):
	top = 4.95
	width, height = HAZE_PIXELS
	x = ((np.arange(width) + 0.5) / width - 0.5)[None, :] * 10
	z = (bottom + (np.arange(height) + 0.5) / height * (top - bottom))[:, None]
	clouds = np.zeros((height, width), np.float32)
	for _ in range(40):
		cx, cz = random.uniform(-5, 5), random.uniform(bottom + 0.4, top)
		sx, sz = random.uniform(0.4, 1.4), random.uniform(0.15, 0.4)
		clouds += random.uniform(0.4, 1) * np.exp(-(((x - cx) / sx) ** 2) - ((z - cz) / sz) ** 2)
	clouds /= clouds.max()
	glow = 0.3 + 0.9 * np.exp(-((x - BULB.x) ** 2 + (y - BULB.y) ** 2 + (z - BULB.z) ** 2) / 1.2 ** 2)
	glow += 0.5 * np.exp(-(np.maximum(np.abs(x) - 3, 0) ** 2 + (y - 0.5) ** 2 + (z - 4.9) ** 2) / 1.0 ** 2)
	density = (0.35 + 0.65 * clouds) * (z - bottom) / (top - bottom) * np.clip((4.7 - np.abs(x)) / 0.8, 0, 1)
	pixels = np.empty((height, width, 4), np.float32)
	pixels[:, :, :3] = (1.0, 0.8, 0.6)
	pixels[:, :, 3] = np.clip(density * glow, 0, 1)
	picture = bpy.data.images.new(f"haze-picture-{i}", width, height, alpha=True)
	picture.pixels.foreach_set(pixels.ravel())
	path = os.path.join(ROOT, "scene", f"haze-{i}.png")
	picture.filepath_raw = path
	picture.file_format = "PNG"
	picture.save()
	bpy.data.images.remove(picture)
	bpy.ops.mesh.primitive_plane_add(size=1, location=(0, y, (bottom + top) / 2), rotation=radians((90, 0, 0)))
	sheet = bpy.context.object
	sheet.name = f"haze-{i}"
	sheet.scale = (10, top - bottom, 1)
	sheet.data.materials.append(overlay(f"haze-{i}", path, HAZE_STRENGTH, additive=True)[0])
	haze_sheets.append(sheet)

# ---------------------------------------------------------------- headphones on a hook

hook = Vector((-3.55, 1.85, 3.55))
box("headphones-hook", hook, (0.08, 0.3, 0.06), rib, bevel=0.01)
band_center = hook + Vector((0, -0.05, -0.38))
bpy.ops.mesh.primitive_torus_add(major_radius=0.34, minor_radius=0.032, major_segments=64, minor_segments=16, location=band_center, rotation=radians((90, 0, 0)))
band = bpy.context.object
band.name = "headphones-band"
mesh = bmesh.new()
mesh.from_mesh(band.data)
bmesh.ops.delete(mesh, geom=[v for v in mesh.verts if v.co.y < -0.08], context="VERTS")
mesh.to_mesh(band.data)
mesh.free()
finish(band, headphone_black, smooth=80)
for side in (-1, 1):
	cup = band_center + Vector((side * 0.33, 0, -0.14))
	cylinder(f"headphones-cup-{side}", cup, 0.14, 0.1, headphone_black, rotation=(0, 90, 0), bevel=0.02)
	torus(f"headphones-cushion-{side}", cup + Vector((-side * 0.06, 0, 0)), 0.11, 0.035, cushion, rotation=(0, 90, 0))
	torus(f"headphones-ring-{side}", cup + Vector((side * 0.051, 0, 0)), 0.1, 0.012, orange, rotation=(0, 90, 0))

# ---------------------------------------------------------------- a banged-up steampunk guitar on the wall

# A T-style solid body (single cutaway, slab), black paint worn through to
# the wood, brass hardware going green, and gadgets: a pressure gauge, a
# copper pipe, gears and a glowing valve. In the guitar's own frame x is
# across, y is depth (towards the wall) and z runs up the guitar.
guitar = bpy.data.objects.new("guitar", None)
scene.collection.objects.link(guitar)
guitar.location = (3.75, 1.66, 1.22)
guitar.rotation_euler = radians((0, -5, 0))
guitar.scale = (0.82, 0.82, 0.82)
bpy.context.view_layer.update()


def slab(name, outline, depth, front_y, mat, bevel=0.0):
	"""A flat shape from an (x, z) outline, extruded back from front_y."""
	data = bpy.data.meshes.new(name)
	mesh = bmesh.new()
	face = mesh.faces.new([mesh.verts.new((x, front_y, z)) for x, z in outline])
	extruded = bmesh.ops.extrude_face_region(mesh, geom=[face])
	bmesh.ops.translate(mesh, vec=(0, depth, 0), verts=[v for v in extruded["geom"] if isinstance(v, bmesh.types.BMVert)])
	bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
	mesh.to_mesh(data)
	mesh.free()
	obj = bpy.data.objects.new(name, data)
	scene.collection.objects.link(obj)
	obj.parent = guitar
	return finish(obj, mat, bevel=bevel, segments=4, smooth=40 if bevel else None)


def patina(scale, amount):
	"""Pattern: green verdigris creeping over brass and copper in patches."""
	def build(nodes, links, colour, position):
		blotches = nodes.new("ShaderNodeTexNoise")
		blotches.inputs["Scale"].default_value = scale
		blotches.inputs["Detail"].default_value = 10
		links.new(position, blotches.inputs["Vector"])
		spread = nodes.new("ShaderNodeMapRange")
		spread.inputs["From Min"].default_value = 0.58
		spread.inputs["From Max"].default_value = 0.7
		spread.inputs["To Max"].default_value = amount
		links.new(blotches.outputs["Fac"], spread.inputs["Value"])
		return mix_colour(nodes, links, spread.outputs["Result"], colour, (0.22, 0.42, 0.33))
	return build


body_paint = worn_paint("guitar-paint", (0.025, 0.025, 0.028), (0.95, 0.75, 0.5))
brass = material("brass", (0.78, 0.56, 0.22), rough=0.35, metal=0.6, scratches=0.3, grime=0.3, dirt=0.4, pattern=patina(9, 0.8))
copper = material("copper", (0.75, 0.38, 0.22), rough=0.35, metal=0.6, scratches=0.2, dirt=0.4, pattern=patina(7, 0.9))
maple = material("maple", (1.25, 1.05, 0.75), rough=0.4, photo="Wood096", photo_size=0.6, grime=0.3, dirt=0.4)
bobbin = material("pickup", (0.02, 0.02, 0.022), rough=0.5, scratches=0.2)
dial_face = material("gauge-face", (0.85, 0.8, 0.65), rough=0.6, grime=0.3)
valve_glow = material("valve", (0, 0, 0), emit=(1.0, 0.5, 0.15), strength=4)
inlay = material("inlay", (0.03, 0.03, 0.03), rough=0.5)

# The body.
BODY = [
	(0.0, 0.0), (0.38, 0.03), (0.58, 0.18), (0.635, 0.45), (0.61, 0.75), (0.55, 0.95), (0.5, 1.08),
	(0.38, 1.13), (0.24, 1.2), (0.15, 1.38), (0.12, 1.55), (-0.22, 1.56), (-0.42, 1.5), (-0.55, 1.35),
	(-0.58, 1.15), (-0.56, 0.95), (-0.6, 0.75), (-0.635, 0.45), (-0.58, 0.18), (-0.38, 0.03),
]
slab("guitar-body", [(p.x, p.y) for p in smooth_loop(BODY)], 0.18, 0, body_paint, bevel=0.03)

# Brass plates: a pickguard round the neck pickup, the bridge, and the controls.
GUARD = [(-0.5, 0.95), (-0.53, 1.25), (-0.38, 1.45), (-0.13, 1.5), (0.11, 1.5), (0.14, 1.36), (0.22, 1.2), (0.08, 1.02), (-0.1, 0.92), (-0.32, 0.88)]
guard = smooth_loop(GUARD, 6)
slab("guitar-guard", [(p.x, p.y) for p in guard], 0.006, -0.006, brass, bevel=0.002)
for i, p in enumerate(guard[::6]):
	inward = (Vector((-0.17, 1.2)) - p).normalized() * 0.03
	sphere(f"guitar-guard-rivet-{i}", (p.x + inward.x, -0.008, p.y + inward.y), 0.011, brass, segments=10, parent=guitar)
box("guitar-bridge", (0, -0.004, 0.42), (0.42, 0.008, 0.3), brass, bevel=0.01, parent=guitar)
for i, x in enumerate((-0.11, 0, 0.11)):
	cylinder(f"guitar-saddle-{i}", (x, -0.022, 0.36), 0.018, 0.11, brass, rotation=(0, 90, 0), vertices=12, parent=guitar)
bridge_pickup = Matrix.Rotation(math.radians(-8), 3, "Y")
box("guitar-pickup-bridge", (0, -0.016, 0.5), (0.32, 0.02, 0.07), bobbin, rotation=(0, -8, 0), bevel=0.008, parent=guitar)
for i in range(6):
	cylinder(f"guitar-pole-{i}", Vector((0, -0.027, 0.5)) + bridge_pickup @ Vector((-0.1 + 0.04 * i, 0, 0)), 0.009, 0.004, nickel, rotation=(90, 0, 0), vertices=10, parent=guitar)
box("guitar-pickup-neck", (0, -0.02, 1.27), (0.3, 0.025, 0.11), brass, bevel=0.02, parent=guitar)
box("guitar-controls", (0.38, -0.006, 0.62), (0.12, 0.012, 0.5), brass, rotation=(0, 20, 0), bevel=0.02, parent=guitar)
along = Matrix.Rotation(math.radians(20), 3, "Y") @ Vector((0, 0, 1))
for i, t in enumerate((-0.12, 0.06)):
	at = Vector((0.38, -0.03, 0.62)) + along * t
	cylinder(f"guitar-knob-{i}", at, 0.045, 0.05, brass, rotation=(90, 0, 0), bevel=0.008, vertices=24, parent=guitar)
switch_at = Vector((0.38, -0.012, 0.62)) + along * 0.2
rod("guitar-switch", switch_at, switch_at + Vector((0.03, -0.06, 0.03)), 0.008, nickel, parent=guitar)
sphere("guitar-switch-tip", switch_at + Vector((0.03, -0.06, 0.03)), 0.018, bobbin, segments=12, parent=guitar)

# A pressure gauge on the lower bout, fed by a copper pipe from the controls.
gauge = Vector((-0.33, -0.012, 0.44))
torus("guitar-gauge-bezel", gauge + Vector((0, -0.01, 0)), 0.105, 0.018, brass, rotation=(90, 0, 0), parent=guitar)
cylinder("guitar-gauge-face", gauge, 0.1, 0.01, dial_face, rotation=(90, 0, 0), vertices=48, parent=guitar)
for i in range(9):
	angle = math.radians(225 - 270 * i / 8)
	box(f"guitar-gauge-tick-{i}", gauge + Vector((math.cos(angle) * 0.075, -0.006, math.sin(angle) * 0.075)), (0.004, 0.002, 0.018), inlay, rotation=(0, 90 - math.degrees(angle), 0), parent=guitar)
needle = math.radians(60)
box("guitar-gauge-needle", gauge + Vector((math.cos(needle) * 0.035, -0.008, math.sin(needle) * 0.035)), (0.07, 0.002, 0.006), material("needle", (0.6, 0.05, 0.03), rough=0.4), rotation=(0, -math.degrees(needle), 0), parent=guitar)
sphere("guitar-gauge-cap", gauge + Vector((0, -0.01, 0)), 0.012, brass, segments=10, parent=guitar)
pipe = [guitar.matrix_world @ Vector(p) for p in ((0.36, -0.03, 0.4), (0.3, -0.035, 0.22), (0.12, -0.035, 0.11), (-0.1, -0.035, 0.12), (-0.26, -0.03, 0.27), (-0.33, -0.03, 0.33))]
cable("guitar-pipe", pipe, 0.013, copper)
for i, p in enumerate((pipe[0], pipe[-1])):
	sphere(f"guitar-pipe-fitting-{i}", p, 0.022, brass, segments=12)

# Gears on the upper horn.
for name, (x, z), radius, teeth in (("big", (-0.38, 1.24), 0.085, 12), ("small", (-0.25, 1.355), 0.05, 8)):
	cylinder(f"guitar-gear-{name}", (x, -0.012, z), radius, 0.014, brass, rotation=(90, 0, 0), vertices=32, parent=guitar)
	for t in range(teeth):
		angle = 2 * math.pi * t / teeth
		box(f"guitar-gear-{name}-tooth-{t}", (x + math.cos(angle) * (radius + 0.008), -0.012, z + math.sin(angle) * (radius + 0.008)), (0.018, 0.014, 0.014), brass, rotation=(0, -math.degrees(angle), 0), parent=guitar)
	cylinder(f"guitar-gear-{name}-hub", (x, -0.022, z), radius * 0.3, 0.012, copper, rotation=(90, 0, 0), vertices=16, parent=guitar)

# A valve on the treble bout, glowing in its brass socket.
cylinder("guitar-valve-socket", (0.33, -0.03, 0.83), 0.04, 0.05, brass, vertices=24, parent=guitar)
cylinder("guitar-valve-glass", (0.33, -0.03, 0.92), 0.03, 0.13, valve_glow, vertices=24, parent=guitar)
sphere("guitar-valve-top", (0.33, -0.03, 0.985), 0.03, valve_glow, segments=16, parent=guitar)

# The neck: worn maple, frets, dots, and a 3+3 brass-plated headstock.
box("guitar-neck", (0, 0.06, 2.15), (0.15, 0.1, 1.45), maple, bevel=0.02, parent=guitar)
box("guitar-fretboard", (0, -0.0, 2.15), (0.15, 0.03, 1.45), maple, parent=guitar)
nut = 2.86
bridge_z = 0.36
scale_length = nut - bridge_z
for fret in range(1, 22):
	z = nut - scale_length * (1 - 2 ** (-fret / 12))
	box(f"guitar-fret-{fret}", (0, -0.018, z), (0.15, 0.006, 0.008), nickel, parent=guitar)
	if fret in (3, 5, 7, 9, 12, 15, 17, 19, 21):
		middle = nut - scale_length * (1 - 2 ** (-(fret - 0.5) / 12))
		for dx in ((-0.035, 0.035) if fret == 12 else (0,)):
			cylinder(f"guitar-dot-{fret}-{dx}", (dx, -0.016, middle), 0.012, 0.004, inlay, rotation=(90, 0, 0), vertices=12, parent=guitar)
box("guitar-nut", (0, -0.012, nut + 0.01), (0.15, 0.025, 0.02), material("bone", (0.85, 0.82, 0.72), rough=0.5), parent=guitar)
box("guitar-head", (0, 0.03, 3.12), (0.27, 0.045, 0.5), maple, rotation=(-6, 0, 0), bevel=0.02, parent=guitar)
box("guitar-head-plate", (0, 0.005, 3.13), (0.23, 0.006, 0.44), brass, rotation=(-6, 0, 0), bevel=0.01, parent=guitar)
for side in (-1, 1):
	for i in range(3):
		z = 2.97 + 0.15 * i
		cylinder(f"guitar-tuner-{side}-{i}", (side * 0.17, 0.03, z), 0.03, 0.035, brass, rotation=(0, 90, 0), vertices=12, parent=guitar)
		cylinder(f"guitar-post-{side}-{i}", (side * 0.06, -0.01, z), 0.012, 0.03, nickel, rotation=(90, 0, 0), vertices=10, parent=guitar)
for i in range(6):
	start = Vector((-0.06 + 0.024 * i, -0.045, bridge_z))
	end = Vector((-0.045 + 0.018 * i, -0.03, nut))
	rod(f"guitar-string-{i}", start, end, 0.0035, nickel, vertices=6, parent=guitar)
box("guitar-hanger", (0, 0.25, 2.88), (0.24, 0.24, 0.05), rib, parent=guitar)

# ---------------------------------------------------------------- outside: Saturn

# Through the viewport at depth y, an object lines up with (x, z) on the wall
# when it sits on the line from the camera through that point. k is how much
# to scale it to keep the size it would have on the wall.
def behind_window(x, z, y):
	k = (y - CAMERA.y) / (WALL_Y - CAMERA.y)
	return Vector((CAMERA.x + (x - CAMERA.x) * k, y, CAMERA.z + (z - CAMERA.z) * k)), k


# Saturn's numbers from NASA's fact sheets: equatorial radius 60,268 km,
# flattening 0.098; ring edges in Saturn radii: C 1.239 to 1.526, B to 1.950,
# Cassini division to 2.030, A to 2.270, Encke gap at 2.214.
saturn_center, k = behind_window(0.55, 3.0, 40)
radius = 0.6 * k
# The pole leans 25 degrees towards the camera, so the rings open about as
# wide as they do in most photos of Saturn, then the whole planet rolls a little.
pole_tilt = (25, -16, 0)


def saturn_latitude(nodes, links):
	"""Coordinate: the shading point's height along Saturn's pole, mapped to 0..1, a little wavy."""
	coords = nodes.new("ShaderNodeTexCoord")
	separate = nodes.new("ShaderNodeSeparateXYZ")
	noise = nodes.new("ShaderNodeTexNoise")
	noise.inputs["Scale"].default_value = 3 / radius
	noise.inputs["Detail"].default_value = 6
	wobble = nodes.new("ShaderNodeMath")
	wobble.operation = "MULTIPLY_ADD"
	wobble.inputs[1].default_value = 0.04 * radius
	remap = nodes.new("ShaderNodeMapRange")
	remap.inputs["From Min"].default_value = -radius * 0.92
	remap.inputs["From Max"].default_value = radius * 0.92
	links.new(coords.outputs["Object"], separate.inputs[0])
	links.new(coords.outputs["Object"], noise.inputs["Vector"])
	links.new(noise.outputs["Fac"], wobble.inputs[0])
	links.new(separate.outputs["Z"], wobble.inputs[2])
	links.new(wobble.outputs["Value"], remap.inputs["Value"])
	return remap.outputs["Result"]


saturn_bands = ramp_material(
	"saturn",
	[
		(0.0, (0.36, 0.4, 0.46), 1),
		(0.14, (0.5, 0.46, 0.38), 1),
		(0.24, (0.74, 0.58, 0.34), 1),
		(0.32, (0.56, 0.38, 0.18), 1),
		(0.4, (0.84, 0.7, 0.44), 1),
		(0.47, (0.95, 0.86, 0.64), 1),
		(0.53, (0.93, 0.82, 0.58), 1),
		(0.6, (0.72, 0.54, 0.3), 1),
		(0.67, (0.86, 0.72, 0.46), 1),
		(0.76, (0.62, 0.46, 0.26), 1),
		(0.86, (0.5, 0.46, 0.38), 1),
		(1.0, (0.36, 0.4, 0.46), 1),
	],
	rough=0.9,
	coordinate=saturn_latitude,
)
saturn = sphere("saturn", saturn_center, 1, saturn_bands, scale=(radius, radius, radius * (1 - 0.098)), rotation=pole_tilt, segments=96)
ring_stops = [
	(0.0, (0, 0, 0), 0),
	(0.035, (0.3, 0.25, 0.19), 0.2),
	(0.29, (0.42, 0.34, 0.25), 0.35),
	(0.296, (0.8, 0.68, 0.48), 0.92),
	(0.5, (0.9, 0.78, 0.56), 1),
	(0.678, (0.74, 0.62, 0.44), 0.95),
	(0.682, (0.05, 0.045, 0.04), 0.08),
	(0.755, (0.64, 0.54, 0.4), 0.8),
	(0.915, (0.6, 0.5, 0.37), 0.75),
	(0.92, (0.1, 0.09, 0.08), 0.15),
	(0.925, (0.58, 0.49, 0.36), 0.7),
	(0.972, (0.55, 0.46, 0.34), 0.65),
	(0.975, (0, 0, 0), 0),
]
rings = ramp_material("rings", ring_stops, rough=0.9, coordinate=distance_from(saturn_center, radius * 1.2, radius * 2.3), alpha=True)
bpy.ops.mesh.primitive_circle_add(vertices=256, radius=radius * 2.3, fill_type="TRIFAN", location=saturn_center, rotation=radians(pole_tilt))
ring_disc = bpy.context.object
ring_disc.name = "saturn-rings"
finish(ring_disc, rings)

# Saturn's six largest moons on the ring plane, at their real distances and
# sizes (NASA: semi-major axis in Saturn radii, mean radius in km, albedo).
# Where each sits along its orbit is made up.
MOONS = [
	("mimas", 3.0783, 198, 0.6, 35),
	("enceladus", 3.9494, 252, 1.0, 160),
	("tethys", 4.8892, 531, 0.8, 300),
	("dione", 6.2620, 561, 0.7, 210),
	("rhea", 8.7449, 763, 0.7, 20),
	("titan", 20.273, 2575, 0.22, 190),
]
ring_axes = saturn.matrix_world.to_3x3().normalized()
moons = []
for name, distance, kilometres, albedo, angle in MOONS:
	theta = math.radians(angle)
	along_rings = ring_axes.col[0] * math.cos(theta) + ring_axes.col[1] * math.sin(theta)
	colour = (0.55, 0.38, 0.18) if name == "titan" else (albedo, albedo, albedo * 0.97)
	moons.append(sphere(f"moon-{name}", saturn_center + along_rings * distance * radius, radius * kilometres / 60268, material(f"moon-{name}", colour, rough=0.9), segments=16))

space_objects = [saturn, ring_disc] + moons

# ---------------------------------------------------------------- light

def light(kind, location, energy, color, size=1.0, size_y=None, target=None, rotation=None):
	data = bpy.data.lights.new(f"{kind.lower()}-light", kind)
	data.energy = energy
	data.color = color
	if kind == "AREA":
		data.shape = "RECTANGLE"
		data.size = size
		data.size_y = size_y or size
	obj = bpy.data.objects.new(data.name, data)
	scene.collection.objects.link(obj)
	obj.location = location
	if target is not None:
		obj.rotation_euler = (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
	if rotation is not None:
		obj.rotation_euler = rotation
	obj.visible_camera = False
	return obj


# Mood: the overhead panel turned well down, so the room is lit mostly by its
# practical lights: warm pools from the desk lamp and the bare bulb against
# the cool of the screens and the window.
light("AREA", (0, 0.5, 4.85), 75, (1.0, 0.7, 0.45), size=6, size_y=1.4, target=(0, 0.5, 0))
light("AREA", (0, -4.5, 3.6), 10, (1.0, 0.82, 0.65), size=6, size_y=2, target=(0, 1.5, 1.5))
hanging = light("POINT", BULB, 180, (1.0, 0.55, 0.26))
hanging.data.shadow_soft_size = 0.03
desk_lamp = light("SPOT", bulb_at, 420, (1.0, 0.64, 0.34), target=lamp_target)
desk_lamp.data.spot_size = math.radians(70)
desk_lamp.data.spot_blend = 0.35
desk_lamp.data.shadow_soft_size = 0.04
light("AREA", lid_center + lid_front * 0.3, 18, (0.7, 0.82, 1.0), size=1.1, size_y=0.7, target=lid_center + lid_front * 2)
# Kept clear of the window's frame: tilted, its lower edge used to reach into
# the opening and light a thin bright arc there that shimmered.
light("AREA", (0, 1.6, WINDOW["z"]), 32, (0.72, 0.8, 1.0), size=WINDOW["width"], size_y=WINDOW["height"], target=(0, -3, 2.4))

# Sunlight for Saturn only: linked so it neither lights nor is blocked by the cabin.
sunlit = bpy.data.collections.new("sunlit")
for obj in [saturn, ring_disc] + moons:
	sunlit.objects.link(obj)
sun = light("SUN", (0, 0, 0), 4.5, (1.0, 0.97, 0.92), target=Vector((1.0, 0.12, -0.2)))
sun.data.angle = math.radians(0.5)
sun.light_linking.receiver_collection = sunlit
sun.light_linking.blocker_collection = sunlit

# The sky: stars and a wash of nebula in every direction, seen by the camera
# but lighting nothing, so the cabin stays lit by its own lamps.
world = bpy.data.worlds.new("space")
nodes = world.node_tree.nodes
links = world.node_tree.links
direction = nodes.new("ShaderNodeTexCoord").outputs["Generated"]
cells = nodes.new("ShaderNodeTexVoronoi")
cells.inputs["Scale"].default_value = 90
links.new(direction, cells.inputs["Vector"])
core = math_node(nodes, links, "POWER", math_node(nodes, links, "MAXIMUM", math_node(nodes, links, "SUBTRACT", 1, math_node(nodes, links, "DIVIDE", cells.outputs["Distance"], 0.09)), 0), 3)
# Only some cells hold a star, at random brightness.
pick = nodes.new("ShaderNodeSeparateColor")
links.new(cells.outputs["Color"], pick.inputs[0])
# The Milky Way: a band around the sky, brightest along its middle.
galactic_pole = nodes.new("ShaderNodeVectorMath")
galactic_pole.operation = "DOT_PRODUCT"
# Tilted so the band crosses the sky behind Saturn, seen through the window.
galactic_pole.inputs[1].default_value = Vector((0.5, 0.08, 0.86)).normalized()
links.new(direction, galactic_pole.inputs[0])
band = nodes.new("ShaderNodeMapRange")
band.inputs["From Min"].default_value = 0.0
band.inputs["From Max"].default_value = 0.22
band.inputs["To Min"].default_value = 1.0
band.inputs["To Max"].default_value = 0.0
links.new(math_node(nodes, links, "ABSOLUTE", galactic_pole.outputs["Value"]), band.inputs["Value"])
in_band = band.outputs["Result"]
# More cells hold a star along the band.
shown = math_node(nodes, links, "GREATER_THAN", pick.outputs[0], math_node(nodes, links, "SUBTRACT", 0.88, math_node(nodes, links, "MULTIPLY", in_band, 0.2)))
brightness = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "MULTIPLY", core, shown), math_node(nodes, links, "ADD", math_node(nodes, links, "MULTIPLY", pick.outputs[1], 9), 1))
nebula = nodes.new("ShaderNodeTexNoise")
nebula.inputs["Scale"].default_value = 1.6
nebula.inputs["Detail"].default_value = 10
links.new(direction, nebula.inputs["Vector"])
haze = nodes.new("ShaderNodeValToRGB")
haze.color_ramp.elements[0].position = 0.45
haze.color_ramp.elements[0].color = (0, 0, 0, 1)
haze.color_ramp.elements[1].position = 0.82
haze.color_ramp.elements[1].color = (0.08, 0.04, 0.13, 1)
links.new(nebula.outputs["Fac"], haze.inputs["Fac"])
# The band's own glow, broken up by dark lanes of dust.
dust = nodes.new("ShaderNodeTexNoise")
dust.inputs["Scale"].default_value = 14
dust.inputs["Detail"].default_value = 12
links.new(direction, dust.inputs["Vector"])
lanes = nodes.new("ShaderNodeMapRange")
lanes.inputs["From Min"].default_value = 0.38
lanes.inputs["From Max"].default_value = 0.6
links.new(dust.outputs["Fac"], lanes.inputs["Value"])
milky = math_node(nodes, links, "MULTIPLY", math_node(nodes, links, "POWER", in_band, 2), lanes.outputs["Result"])
milky_colour = nodes.new("ShaderNodeVectorMath")
milky_colour.operation = "SCALE"
milky_colour.inputs[0].default_value = (0.09, 0.085, 0.08)
links.new(milky, milky_colour.inputs["Scale"])
haze_and_band = nodes.new("ShaderNodeVectorMath")
haze_and_band.operation = "ADD"
links.new(haze.outputs["Color"], haze_and_band.inputs[0])
links.new(milky_colour.outputs["Vector"], haze_and_band.inputs[1])
glow = nodes.new("ShaderNodeVectorMath")
glow.operation = "ADD"
links.new(brightness, glow.inputs[0])
links.new(haze_and_band.outputs["Vector"], glow.inputs[1])
sky_light = nodes["Background"]
links.new(glow.outputs["Vector"], sky_light.inputs["Color"])
darkness = nodes.new("ShaderNodeBackground")
darkness.inputs["Color"].default_value = (0, 0, 0, 1)
camera_only = nodes.new("ShaderNodeMixShader")
links.new(nodes.new("ShaderNodeLightPath").outputs["Is Camera Ray"], camera_only.inputs["Fac"])
links.new(darkness.outputs["Background"], camera_only.inputs[1])
links.new(sky_light.outputs["Background"], camera_only.inputs[2])
links.new(camera_only.outputs["Shader"], nodes["World Output"].inputs["Surface"])
scene.world = world

# ---------------------------------------------------------------- camera and render settings

camera_data = bpy.data.cameras.new("camera")
camera_data.lens = LENS
camera_data.clip_end = 1000
camera = bpy.data.objects.new("camera", camera_data)
scene.collection.objects.link(camera)
camera.location = CAMERA
camera.rotation_euler = (CAMERA_TARGET - CAMERA).to_track_quat("-Z", "Y").to_euler()
scene.camera = camera

scene.render.engine = "CYCLES"
cycles_prefs = bpy.context.preferences.addons["cycles"].preferences
try:
	cycles_prefs.compute_device_type = "METAL"
	cycles_prefs.get_devices()
	for device in cycles_prefs.devices:
		device.use = True
	scene.cycles.device = "GPU"
except TypeError:
	scene.cycles.device = "CPU"
scene.cycles.use_denoising = True
for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
	try:
		scene.view_settings.look = look
		break
	except TypeError:
		pass
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
bpy.context.view_layer.update()

# ---------------------------------------------------------------- hotspots

def hotspot(prefix):
	"""Where a prop sits in the still (percent of the frame) and in the scene (three.js axes)."""
	parts = [obj for obj in scene.objects if obj.type == "MESH" and obj.name.startswith(prefix)]
	corners = [obj.matrix_world @ Vector(corner) for obj in parts for corner in obj.bound_box]
	seen = [world_to_camera_view(scene, camera, corner) for corner in corners]
	left = min(p.x for p in seen)
	right = max(p.x for p in seen)
	top = 1 - max(p.y for p in seen)
	bottom = 1 - min(p.y for p in seen)
	center = sum(corners, Vector()) / len(corners)
	return {
		"left": round(left * 100, 2),
		"top": round(top * 100, 2),
		"width": round((right - left) * 100, 2),
		"height": round((bottom - top) * 100, 2),
		"center": [round(center.x, 3), round(center.z, 3), round(-center.y, 3)],
	}


PROPS = {
	"laptop": "laptop",
	"mug": "mug",
	"phone": "phone",
	"headphones": "headphones",
	"guitar": "guitar",
	"window": "window-frame",
	"plant": "plant",
	"notebook": "notebook",
	"morse": "morse",
	"poster": "poster",
	"discs": "disc",
	"sanitiser": "sanitiser",
	"pens": "cup",
	"notes": "postit",
	"gravity": "gravity",
	"panel": "simon",
}
hotspots = {name: hotspot(prefix) for name, prefix in PROPS.items()}
# The laptop screen's corners, for the post list laid over it in HTML.
# Its scale is applied, so the mesh's own vertices are the corners; sorted
# top-left, top-right, bottom-right, bottom-left as the camera sees them.
seen = [world_to_camera_view(scene, camera, screen.matrix_world @ v.co) for v in screen.data.vertices]
seen = [(p.x * 100, (1 - p.y) * 100) for p in seen]
top = sorted(sorted(seen, key=lambda p: p[1])[:2])
bottom = sorted(sorted(seen, key=lambda p: p[1])[2:])
hotspots["screen"] = [[round(x, 2), round(y, 2)] for x, y in (top[0], top[1], bottom[1], bottom[0])]
beacon_at, _ = behind_window(*BEACON, 40)
beacon = world_to_camera_view(scene, camera, beacon_at)
hotspots["beacon"] = {"left": round(beacon.x * 100, 2), "top": round((1 - beacon.y) * 100, 2)}
# The bare bulb, so the live scene can match its colour in the still.
bulb_seen = world_to_camera_view(scene, camera, BULB)
hotspots["bulb"] = {"left": round(bulb_seen.x * 100, 2), "top": round((1 - bulb_seen.y) * 100, 2)}
# And the phone's screen, so the live scene can start from its colour.
phone_seen = world_to_camera_view(scene, camera, phone_screen.matrix_world.translation)
hotspots["phone-screen"] = {"left": round(phone_seen.x * 100, 2), "top": round((1 - phone_seen.y) * 100, 2)}
# And the panel's buttons and lamp: the live scene lights them from these colours.
for obj in simon_buttons + [simon_lamp]:
	seen_at = world_to_camera_view(scene, camera, obj.matrix_world.translation)
	hotspots[obj.name] = {"left": round(seen_at.x * 100, 2), "top": round((1 - seen_at.y) * 100, 2)}
# And the gravity lamp, for the same reason.
lamp_seen = world_to_camera_view(scene, camera, gravity_lamp.location)
hotspots["gravity-lamp"] = {"left": round(lamp_seen.x * 100, 2), "top": round((1 - lamp_seen.y) * 100, 2)}
# Invisible boxes around each prop: the live scene picks props with these.
hits = []
for name, prefix in PROPS.items():
	parts = [obj for obj in scene.objects if obj.type == "MESH" and obj.name.startswith(prefix)]
	corners = [obj.matrix_world @ Vector(corner) for obj in parts for corner in obj.bound_box]
	low = Vector([min(c[i] for c in corners) - 0.03 for i in range(3)])
	high = Vector([max(c[i] for c in corners) + 0.03 for i in range(3)])
	bpy.ops.mesh.primitive_cube_add(size=1, location=(low + high) / 2)
	hit = bpy.context.object
	hit.name = f"hit-{name}"
	hit.scale = high - low
	hit.hide_render = True
	hits.append(hit)

# Where the light in the window is, for the live scene: along the line from
# the camera through its spot on the wall, out near the sky.
beacon_marker = bpy.data.objects.new("beacon", None)
scene.collection.objects.link(beacon_marker)
beacon_marker.location = CAMERA + (Vector((BEACON[0], WALL_Y, BEACON[1])) - CAMERA).normalized() * 380
# Where the live scene puts its steam (over the coffee) and its dust (in the
# desk lamp's beam, from the bulb to the middle of its pool of light).
for name, at in (("steam", (0.75, 0.25, DESK_Z + 0.3)), ("dust-from", bulb_at), ("dust-to", lamp_target)):
	marker = bpy.data.objects.new(name, None)
	scene.collection.objects.link(marker)
	marker.location = at

# What things thrown about in the live scene bounce off: the inside of the
# room (back to the window glass) and the desk, down to the floor. Boxes as
# [lowest corner, highest corner] in three.js axes.
def three_box(low, high):
	return [[round(low.x, 3), round(low.z, 3), round(-high.y, 3)], [round(high.x, 3), round(high.z, 3), round(-low.y, 3)]]


desk_corners = [bpy.data.objects["desk-top"].matrix_world @ Vector(corner) for corner in bpy.data.objects["desk-top"].bound_box]
bounds = {
	"room": three_box(Vector((-4.7, ROOM_FRONT, 0)), Vector((4.7, GLASS_Y, 4.95))),
	"desk": three_box(
		Vector((min(c.x for c in desk_corners), min(c.y for c in desk_corners), 0)),
		Vector((max(c.x for c in desk_corners), max(c.y for c in desk_corners), max(c.z for c in desk_corners))),
	),
}
os.makedirs(os.path.join(ROOT, "src", "data"), exist_ok=True)
with open(os.path.join(ROOT, "src", "data", "cabin.json"), "w") as file:
	json.dump({"still": {"width": 1920, "height": 1080}, "hotspots": hotspots, "bounds": bounds}, file, indent="\t")
	file.write("\n")

# ---------------------------------------------------------------- the still and the share card

scene.cycles.samples = 64 if FAST else 256
scene.render.image_settings.file_format = "WEBP"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.quality = 82
scene.render.filepath = os.path.join(ROOT, "public", "cabin-still.webp")
bpy.ops.render.render(write_still=True)

if not FAST:
	scene.render.resolution_x = 1200
	scene.render.resolution_y = 630
	scene.render.image_settings.file_format = "JPEG"
	scene.render.image_settings.quality = 85
	scene.render.filepath = os.path.join(ROOT, "public", "og.jpg")
	bpy.ops.render.render(write_still=True)
	scene.render.resolution_x = 1920
	scene.render.resolution_y = 1080

# ---------------------------------------------------------------- space, for the live scene

def render_alone(keep, path, file_format, pixels=None, percentage=100):
	"""Render only the objects in keep (plus the sky), then save with the
	scene's colour grading applied, like the still."""
	hidden = [obj for obj in scene.objects if obj.type in {"MESH", "FONT"} and obj not in keep and not obj.hide_render]
	for obj in hidden:
		obj.hide_render = True
	if pixels:
		scene.render.resolution_x, scene.render.resolution_y = pixels
	scene.render.resolution_percentage = percentage
	bpy.ops.render.render()
	scene.render.image_settings.file_format = file_format
	bpy.data.images["Render Result"].save_render(path, scene=scene)
	scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
	scene.render.resolution_percentage = 100
	for obj in hidden:
		obj.hide_render = False


# Saturn and its rings as one sharp picture with a transparent background, on
# a card far out along the line of sight. It's drawn at 2.5 times the still's
# resolution, so it stays crisp when you fly up to the window.
seen = [world_to_camera_view(scene, camera, obj.matrix_world @ Vector(corner)) for obj in (saturn, ring_disc) for corner in obj.bound_box]
x0 = max(0.0, min(p.x for p in seen) - 0.01)
x1 = min(1.0, max(p.x for p in seen) + 0.01)
y0 = max(0.0, min(p.y for p in seen) - 0.01)
y1 = min(1.0, max(p.y for p in seen) + 0.01)
scene.render.film_transparent = True
scene.render.use_border = True
scene.render.use_crop_to_border = True
scene.render.border_min_x, scene.render.border_max_x = x0, x1
scene.render.border_min_y, scene.render.border_max_y = y0, y1
# PNG first: the share card left the format on JPEG, which has no transparency.
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
saturn_path = os.path.join(ROOT, "scene", "saturn.png")
render_alone([saturn, ring_disc], saturn_path, "PNG", percentage=100 if FAST else 250)
scene.render.film_transparent = False
scene.render.use_border = False
scene.render.image_settings.color_mode = "RGB"

CARD_DEPTH = 380.0
frame_width = CARD_DEPTH * camera_data.sensor_width / LENS
frame_height = frame_width * 1080 / 1920
bpy.ops.mesh.primitive_plane_add(size=1)
card = bpy.context.object
card.name = "saturn-card"
card.matrix_world = camera.matrix_world @ Matrix.Translation((
	(-0.5 + (x0 + x1) / 2) * frame_width,
	(-0.5 + (y0 + y1) / 2) * frame_height,
	-CARD_DEPTH,
)) @ Matrix.Diagonal(((x1 - x0) * frame_width, (y1 - y0) * frame_height, 1, 1))
card_material = bpy.data.materials.new("saturn-card")
picture = card_material.node_tree.nodes.new("ShaderNodeTexImage")
picture.image = bpy.data.images.load(saturn_path)
card_bsdf = card_material.node_tree.nodes["Principled BSDF"]
card_material.node_tree.links.new(picture.outputs["Color"], card_bsdf.inputs["Base Color"])
card_material.node_tree.links.new(picture.outputs["Alpha"], card_bsdf.inputs["Alpha"])
card.data.materials.append(card_material)
card.hide_render = True

# ---------------------------------------------------------------- the passing ship

# The ship that comes past once the song's been played, seen side on, its
# hull number (715120: G O A T, as letter numbers) painted large on its flank. It's 45 m out, lit by the sun and its own hull
# floodlights, and drawn as a sharp picture on a card like Saturn's, about
# 1,600 pixels across, so the number reads when you zoom in from the window
# and not before. The live scene loads the picture only when the ship comes.
# It glides in from SHIP_FROM to SHIP_AT, both (x, z) on the back wall as the
# camera sees them: across in front of Saturn, to hold station left of it.
SHIP_AT = (-1.35, 2.75)
SHIP_FROM = (2.65, 2.75)
SHIP_DEPTH = 45.0
ship_spot = Vector((SHIP_AT[0], WALL_Y, SHIP_AT[1]))
toward_camera = (CAMERA - ship_spot).normalized()
ship_place = CAMERA - toward_camera * SHIP_DEPTH
# Its nose points the way it's going (towards -x); its left flank faces the camera.
tail = (Vector((1, 0, 0)) - toward_camera * toward_camera.x).normalized()
flank = -toward_camera
ship = bpy.data.objects.new("ship", None)
scene.collection.objects.link(ship)
ship.matrix_world = Matrix.Translation(ship_place) @ Matrix((tail, flank, tail.cross(flank))).transposed().to_4x4()
bpy.context.view_layer.update()
# GOAT Capital's conference liner: an old ore hauler the investors bought
# cheap and did up, a long battered red hull with whatever they wanted
# bolted on wherever it fitted. Its bolt-ons are placed by a random number
# generator of its own, so the rest of the scene's random choices don't move.
# Parts are placed in its own terms: nose towards -x, the flank the camera
# sees at -y, up +z. It's built a little larger than it's shown (SHIP_SCALE).
SHIP_SCALE = 0.78
ship.scale = (SHIP_SCALE,) * 3
bpy.context.view_layer.update()
bolt_ons = random.Random(715120)
ship_red = material("ship-red", (0.5, 0.06, 0.045), rough=0.55, grime=0.45, scratches=0.08, dirt=0.45, pattern=grid(0.5, 0.012, (0.26, 0.035, 0.03), axes=("X", "Y", "Z")))
ship_grey = material("ship-grey", (0.5, 0.5, 0.47), rough=0.5, grime=0.4, scratches=0.25, dirt=0.4)
ship_dark = material("ship-dark", (0.1, 0.1, 0.11), rough=0.4, metal=0.5, scratches=0.2, dirt=0.3)
ship_glow = material("ship-glow", (0, 0, 0), emit=(0.45, 0.8, 1.0), strength=6)
ship_lit = material("ship-window", (0, 0, 0), emit=(1.0, 0.82, 0.5), strength=2.5)
ship_unlit = material("ship-window-dark", (0.03, 0.035, 0.04), rough=0.15)
ship_paints = [ship_grey, material("ship-yellow", (0.75, 0.55, 0.08), rough=0.5, grime=0.4), material("ship-blue", (0.16, 0.24, 0.32), rough=0.5, grime=0.4), material("ship-rust", (0.35, 0.16, 0.07), rough=0.7, grime=0.5)]
ship_parts = [
	box("ship-hull", (0, 0, 0), (4.4, 0.8, 0.8), ship_red, bevel=0.12, parent=ship),
	box("ship-keel", (0.25, 0, -0.5), (3.4, 0.5, 0.3), ship_grey, bevel=0.06, parent=ship),
	sphere("ship-nose", (-2.15, 0, 0.04), 1, ship_red, scale=(0.62, 0.4, 0.42), parent=ship),
	box("ship-cockpit", (-2.25, -0.35, 0.2), (0.42, 0.04, 0.11), material("ship-cockpit", (0.01, 0.015, 0.02), rough=0.5, emit=(0.1, 0.35, 0.75), strength=1.2), parent=ship),
	box("ship-bumper", (-2.62, 0, -0.18), (0.22, 0.46, 0.2), ship_paints[1], bevel=0.03, parent=ship),
	sphere("ship-dome", (-0.25, 0, 0.36), 1, material("ship-dome", (0.02, 0.025, 0.03), rough=0.05, emit=(0.9, 0.4, 0.12), strength=0.6), scale=(0.75, 0.32, 0.36), parent=ship),
	box("ship-fin", (1.65, 0, 0.72), (1.0, 0.05, 0.6), ship_red, rotation=(0, -15, 0), bevel=0.02, parent=ship),
	box("ship-engine-block", (2.45, 0, 0), (0.5, 0.86, 0.84), ship_dark, bevel=0.06, parent=ship),
]
# Three engines that don't match: a big one in the middle, two small ones
# above and below. Each ends in a glowing nozzle, where the live scene's
# plume starts (SHIP_NOZZLES).
SHIP_NOZZLES = []
for i, (z, radius, length) in enumerate([(0.05, 0.28, 0.5), (0.47, 0.13, 0.36), (-0.4, 0.15, 0.42)]):
	x = 2.7 + length / 2
	ship_parts.append(cylinder(f"ship-engine-{i}", (x, 0, z), radius, length, ship_dark, rotation=(0, 90, 0), bevel=0.02, parent=ship))
	ship_parts.append(cylinder(f"ship-nozzle-{i}", (x + length / 2 + 0.005, 0, z), radius * 0.82, 0.01, ship_glow, rotation=(0, 90, 0), parent=ship))
	SHIP_NOZZLES.append((Vector((x + length / 2 + 0.01, 0, z)), radius))
# Bolt-ons: containers, tanks and boxes along the top behind the dome and
# under the keel, in mismatched paint, a dish on a mast, and antennas.
for i in range(6):
	x = bolt_ons.uniform(0.5, 2.0) if i < 4 else bolt_ons.uniform(-1.4, 1.6)
	top = i < 4
	size = (bolt_ons.uniform(0.35, 0.75), bolt_ons.uniform(0.3, 0.6), bolt_ons.uniform(0.18, 0.34))
	z = 0.4 + size[2] / 2 if top else -0.65 - size[2] / 2
	paint = bolt_ons.choice(ship_paints)
	if bolt_ons.random() < 0.35:
		ship_parts.append(cylinder(f"ship-tank-{i}", (x, 0, z), size[2] / 2 + 0.03, size[0], paint, rotation=(0, 90, 0), bevel=0.02, parent=ship))
	else:
		ship_parts.append(box(f"ship-module-{i}", (x, 0, z), size, paint, bevel=0.03, parent=ship))
ship_parts.append(cylinder("ship-mast", (-1.15, 0, 0.62), 0.025, 0.5, ship_grey, parent=ship))
ship_parts.append(sphere("ship-dish", (-1.15, 0, 0.92), 0.22, ship_grey, scale=(1, 1, 0.35), rotation=(0, -35, 0), parent=ship))
for i in range(3):
	x, height = bolt_ons.uniform(-0.9, 1.2), bolt_ons.uniform(0.3, 0.7)
	ship_parts.append(cylinder(f"ship-antenna-{i}", (x, 0.1, 0.4 + height / 2), 0.012, height, ship_grey, vertices=8, parent=ship))
for i in range(7):
	ship_parts.append(box(f"ship-radiator-{i}", (-0.9 + i * 0.16, 0, -0.78), (0.035, 0.42, 0.28), ship_grey, parent=ship))
# Its attitude thrusters, small blocks the live scene puffs from (SHIP_THRUSTERS).
SHIP_THRUSTERS = [Vector(at) for at in [(-2.3, -0.2, 0.42), (-2.25, -0.2, -0.38), (2.2, -0.45, 0.45), (1.9, -0.3, -0.72)]]
for i, at in enumerate(SHIP_THRUSTERS):
	ship_parts.append(box(f"ship-thruster-{i}", at, (0.1, 0.1, 0.08), ship_dark, parent=ship))
# Passenger windows along both decks, some lit, some not.
for deck, (z, y, x_from, x_to) in enumerate([(0.27, -0.405, -0.75, 2.05), (-0.5, -0.255, -1.25, 1.9)]):
	x = x_from
	while x < x_to:
		ship_parts.append(box(f"ship-window-{deck}-{len(ship_parts)}", (x, y, z), (0.09, 0.01, 0.07), ship_lit if bolt_ons.random() < 0.72 else ship_unlit, parent=ship))
		x += 0.17
# Navigation lights: red on the nose, green on the fin, a white strobe on
# the tail. The live scene lights and blinks them (SHIP_LIGHTS).
SHIP_LIGHTS = [((-2.55, -0.2, -0.05), "red"), ((1.85, -0.03, 1.02), "green"), ((2.55, -0.2, 0.48), "white")]
for i, (at, colour) in enumerate(SHIP_LIGHTS):
	ship_parts.append(sphere(f"ship-light-{colour}", at, 0.04, ship_dark, segments=12, parent=ship))
# The livery: the hull number large on the flank, and GOAT Capital's name
# and logo by the nose: the registry's one-bit goat (src/scripts/laptop.js),
# drawn with the same shapes.
def goat_picture(path):
	width, height, grow = 64, 40, 8
	X, Y = np.meshgrid(np.arange(width * grow) / grow + 0.5 / grow, np.arange(height * grow) / grow + 0.5 / grow)
	inside = np.zeros(X.shape, bool)
	def blob(cx, cy, rx, ry, turn=0.0):
		dx, dy = X - cx, Y - cy
		u = (dx * math.cos(turn) + dy * math.sin(turn)) / rx
		v = (-dx * math.sin(turn) + dy * math.cos(turn)) / ry
		return u * u + v * v <= 1
	def shape(points):
		hit = np.zeros(X.shape, bool)
		for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
			crosses = (ay > Y) != (by > Y)
			at = ax + (Y - ay) * (bx - ax) / np.where(by == ay, 1e-9, by - ay)
			hit ^= crosses & (X < at)
		return hit
	inside |= blob(38, 20, 15, 7.5)
	inside |= shape([(25, 15), (18, 7), (14, 10), (23, 22)])
	inside |= blob(14, 10, 5.5, 3.4, -0.45)
	inside |= blob(8.5, 13.2, 3.4, 2.1, -0.55)
	inside |= shape([(8, 14.5), (11, 15), (8.5, 20.5)])
	inside |= shape([(16, 8), (22.5, 9.5), (16.5, 10.5)])
	angle = np.mod(np.arctan2(Y - 9.5, X - 19.5), 2 * math.pi)
	inside |= (np.abs(np.hypot(X - 19.5, Y - 9.5) - 5.5) <= 1.1) & (angle >= math.pi * 1.12) & (angle <= math.pi * 1.8)
	for x in (26, 30, 43, 47):
		inside |= (X >= x) & (X < x + 2.6) & (Y >= 24) & (Y < 36)
	inside |= shape([(52, 16), (56, 10.5), (54, 17.5)])
	inside &= ~((X >= 12) & (X < 13.6) & (Y >= 8.6) & (Y < 10.2))
	# One-bit, as on the terminal: whole pixels on or off.
	cells = inside.reshape(height, grow, width, grow).mean(axis=(1, 3)) > 0.5
	pixels = np.zeros((height * grow, width * grow, 4), np.float32)
	pixels[np.repeat(np.repeat(cells, grow, 0), grow, 1)] = (0.95, 0.92, 0.85, 1)
	picture = bpy.data.images.new("goat-logo", width * grow, height * grow, alpha=True)
	picture.pixels = pixels[::-1].ravel()
	picture.filepath_raw = path
	picture.file_format = "PNG"
	picture.save()
	return path
logo = material("ship-logo", (1, 1, 1), rough=0.6)
logo_texture = logo.node_tree.nodes.new("ShaderNodeTexImage")
logo_texture.image = bpy.data.images.load(goat_picture(os.path.join(ROOT, "scene", "goat-logo.png")))
logo_bsdf = logo.node_tree.nodes["Principled BSDF"]
logo.node_tree.links.new(logo_texture.outputs["Color"], logo_bsdf.inputs["Base Color"])
logo.node_tree.links.new(logo_texture.outputs["Alpha"], logo_bsdf.inputs["Alpha"])
bpy.ops.mesh.primitive_plane_add(size=1, location=(-1.15, -0.406, 0.08), rotation=(math.pi / 2, 0, 0))
goat_decal = bpy.context.object
goat_decal.name = "ship-logo"
goat_decal.scale = (0.56, 0.35, 1)
goat_decal.data.materials.append(logo)
goat_decal.parent = ship
ship_parts.append(goat_decal)
paint_white = material("ship-white", (0.9, 0.88, 0.82), rough=0.6)
for name, text, at, size, paint in [("ship-name", "GOAT CAPITAL", (-1.15, -0.407, -0.2), 0.11, paint_white), ("ship-number", "715120", (0.55, -0.407, -0.03), 0.34, material("ship-ink", (0.03, 0.03, 0.035), rough=0.6))]:
	lettering = stencil(name, text, at, (0, -1, 0), size, paint, typeface=anton)
	lettering.parent = ship
	ship_parts.append(lettering)
for obj in ship_parts:
	obj.hide_render = True
	sunlit.objects.link(obj)
# Its floodlights on the flank, so the number's lit from the camera's side.
shiplit = bpy.data.collections.new("shiplit")
for obj in ship_parts:
	shiplit.objects.link(obj)
floodlight = light("SUN", (0, 0, 0), 2.2, (1.0, 0.95, 0.88), target=ship_place + Vector((0.5, 0, -0.3)) - CAMERA)
floodlight.light_linking.receiver_collection = shiplit
# Only the ship casts shadows for it: the cabin's wall is in its way.
floodlight.light_linking.blocker_collection = shiplit
bpy.context.view_layer.update()

# Its picture, cropped round it and drawn big.
seen = [world_to_camera_view(scene, camera, obj.matrix_world @ Vector(corner)) for obj in ship_parts for corner in obj.bound_box]
x0, x1 = min(p.x for p in seen) - 0.004, max(p.x for p in seen) + 0.004
y0, y1 = min(p.y for p in seen) - 0.004, max(p.y for p in seen) + 0.004
scene.render.film_transparent = True
scene.render.use_border = True
scene.render.use_crop_to_border = True
scene.render.border_min_x, scene.render.border_max_x = x0, x1
scene.render.border_min_y, scene.render.border_max_y = y0, y1
scene.render.image_settings.file_format = "WEBP"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.quality = 85
for obj in ship_parts:
	obj.hide_render = False
render_alone(ship_parts, os.path.join(ROOT, "public", "scene", "ship.webp"), "WEBP", percentage=math.ceil((80000 if FAST else 160000) / ((x1 - x0) * 1920)))
for obj in ship_parts:
	obj.hide_render = True
scene.render.film_transparent = False
scene.render.use_border = False
scene.render.image_settings.color_mode = "RGB"


def frame_card(name, left, right, low, high, depth):
	"""A plane covering part of the camera's frame, from left to right and low
	to high (0 to 1 across the frame), depth along its line of sight."""
	width = depth * camera_data.sensor_width / LENS
	height = width * 1080 / 1920
	bpy.ops.mesh.primitive_plane_add(size=1)
	plane = bpy.context.object
	plane.name = name
	plane.matrix_world = camera.matrix_world @ Matrix.Translation((
		(-0.5 + (left + right) / 2) * width,
		(-0.5 + (low + high) / 2) * height,
		-depth,
	)) @ Matrix.Diagonal(((right - left) * width, (high - low) * height, 1, 1))
	plane.hide_render = True
	return plane


ship_card = frame_card("ship-card", x0, x1, y0, y1, SHIP_DEPTH)
ship_card.data.materials.append(material("ship-card", (1, 1, 1)))
# Where it comes in from: the same card, moved to SHIP_FROM.
start_seen = world_to_camera_view(scene, camera, Vector((SHIP_FROM[0], WALL_Y, SHIP_FROM[1])))
end_seen = world_to_camera_view(scene, camera, ship_spot)
ship_start = bpy.data.objects.new("ship-start", None)
scene.collection.objects.link(ship_start)
ship_start.location = frame_card("ship-start-probe", x0 + start_seen.x - end_seen.x, x1 + start_seen.x - end_seen.x, y0, y1, SHIP_DEPTH).matrix_world.translation
bpy.data.objects.remove(bpy.data.objects["ship-start-probe"])
# Where its engines, thrusters and lights are on its card, for the live scene
# (cabin.js): x from -0.5 to 0.5 across ship.webp, z from -0.5 at its top to
# 0.5 at its bottom; nozzle sizes in metres, as it's shown.
def on_ship_card(local):
	seen_at = world_to_camera_view(scene, camera, ship.matrix_world @ local)
	return {"x": round((seen_at.x - x0) / (x1 - x0) - 0.5, 4), "z": round((y1 - seen_at.y) / (y1 - y0) - 0.5, 4)}
with open(os.path.join(ROOT, "src", "data", "cabin.json")) as file:
	cabin_data = json.load(file)
cabin_data["ship"] = {
	"nozzles": [{**on_ship_card(at), "radius": round(radius * SHIP_SCALE, 3)} for at, radius in SHIP_NOZZLES],
	"thrusters": [on_ship_card(at) for at in SHIP_THRUSTERS],
	"lights": [{**on_ship_card(Vector(at)), "colour": colour} for at, colour in SHIP_LIGHTS],
}
with open(os.path.join(ROOT, "src", "data", "cabin.json"), "w") as file:
	json.dump(cabin_data, file, indent="\t")

# Everything else out there (stars, nebula, the moons) as a 360 degree
# panorama from the camera's usual spot. The live scene shows it as its
# background, infinitely far away. It faces three.js's conventions: the
# middle of the picture looks along +X, with +Z (three.js's +Y) up.
panorama_data = bpy.data.cameras.new("panorama")
panorama_data.type = "PANO"
try:
	panorama_data.panorama_type = "EQUIRECTANGULAR"
except AttributeError:
	panorama_data.cycles.panorama_type = "EQUIRECTANGULAR"
panorama_data.clip_end = 1000
panorama = bpy.data.objects.new("panorama", panorama_data)
scene.collection.objects.link(panorama)
panorama.matrix_world = Matrix.Translation(CAMERA) @ Matrix(((0, 0, -1), (-1, 0, 0), (0, 1, 0))).to_4x4()
scene.camera = panorama
scene.cycles.samples = 32 if FAST else 96
scene.render.image_settings.quality = 80
render_alone(moons, os.path.join(ROOT, "public", "scene", "sky.webp"), "WEBP", pixels=(2048, 1024) if FAST else (6144, 3072))
scene.camera = camera
bpy.data.objects.remove(panorama)

# ---------------------------------------------------------------- bake the cabin

# Everything inside joins into one mesh with one texture. The outsides of the
# walls, floor and ceiling can't be seen from in the room, so they're dropped
# first and the texture spends its pixels on what can.
for name in ("back-wall", "wall-left", "wall-right", "floor", "ceiling"):
	shell = bpy.data.objects[name]
	mesh = bmesh.new()
	mesh.from_mesh(shell.data)
	matrix = shell.matrix_world
	outward = [face for face in mesh.faces if (matrix.to_3x3() @ face.normal).dot(matrix @ face.calc_center_median() - ROOM_CENTER) > 0]
	bmesh.ops.delete(mesh, geom=outward, context="FACES")
	mesh.to_mesh(shell.data)
	mesh.free()

# Loose things float when the live scene's gravity is switched off, so each
# stays out of the joined cabin as an object of its own, baked into the same
# texture. They're named float-<prop>-<n>; n 0 takes the prop's picking box
# along with it. The lever stays apart too, so it can swing, turning on its pivot.
FLOATERS = {
	"float-mug-0": ["mug", "mug-coffee", "mug-handle"],
	"float-pens-0": ["cup-body"],
	**{f"float-pens-{i + 1}": [f"cup-pen-{i}", f"cup-pen-{i}-cap"] for i in range(len(PENS))},
	f"float-pens-{len(PENS) + 1}": ["cup-pencil", "cup-pencil-eraser"],
	f"float-pens-{len(PENS) + 2}": ["cup-marker", "cup-marker-band"],
	"float-notebook-0": ["notebook", "notebook-pages", "notebook-band"],
	"float-notebook-1": ["notebook-pen"],
	"float-discs-0": ["disc-loose", "disc-hub", "disc-loose-label"],
	**{f"float-discs-{i + 1}": [f"disc-case-{i}", f"disc-cover-{i}", f"disc-insert-{i}"] + DISC_PARTS[i] for i in range(3)},
	"float-sanitiser-0": [obj.name for obj in scene.objects if obj.type == "MESH" and obj.name.startswith("sanitiser")],
	"float-plant-0": [obj.name for obj in scene.objects if obj.type == "MESH" and obj.name.startswith("plant-")],
	"float-biscuit-0": ["biscuit"],
	"float-paper-0": ["paper-ball"],
	"float-pick-0": ["pick"],
	"gravity-lever": ["gravity-lever", "gravity-lever-knob"],
}
movable = []
for name, parts in FLOATERS.items():
	for other in bpy.context.selected_objects:
		other.select_set(False)
	for part in parts:
		bpy.data.objects[part].select_set(True)
	bpy.context.view_layer.objects.active = bpy.data.objects[parts[0]]
	if len(parts) > 1:
		bpy.ops.object.join()
	thing = bpy.context.view_layer.objects.active
	thing.name = name
	bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
	if name == "gravity-lever":
		scene.cursor.location = LEVER_PIVOT
		bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
	else:
		bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
	movable.append(thing)

outside = space_objects + ship_parts + [screen, phone_screen, card, ship_card, glass, bulb, gravity_lamp, simon_lamp] + simon_buttons + haze_sheets + hits + movable
for other in bpy.context.selected_objects:
	other.select_set(False)
interior = [obj for obj in scene.objects if obj.type == "MESH" and obj not in outside]
for obj in interior:
	obj.select_set(True)
cabin = back
bpy.context.view_layer.objects.active = cabin
bpy.ops.object.join()
cabin.name = "cabin"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# The loose things and the lever are unwrapped and packed with the cabin, into one texture.
for thing in movable:
	thing.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002)
bpy.ops.object.mode_set(mode="OBJECT")
# Walls and the desk are big and plain; shrinking their islands before packing
# leaves more of the texture for the props.
# The window frame's worn paint keeps more, for its scratches.
# Small lettering grows instead, or its letters take colour from their
# neighbours in the texture and break up when zoomed in on.
island_scale = {"cream-panel": 0.45, "desk-mat": 0.45, "charcoal": 0.45, "rib": 0.45, "frame-paint": 0.75}
island_scale |= {"stencil-cream": 4, "poster-venue": 4, "poster-small": 8, "book-ink-dark": 4, "book-ink-light": 4}
# The loose things pack into the same texture; their marker lettering grows too.
loose_scale = {"marker-ink": 12, "disc-sticker": 3}
assert set(island_scale) <= {mat.name for mat in cabin.data.materials}, "island_scale names a material the cabin doesn't have"
assert set(loose_scale) <= {mat.name for thing in movable for mat in thing.data.materials}, "loose_scale names a material no loose thing has"
for thing, scale in [(cabin, island_scale)] + [(thing, loose_scale) for thing in movable]:
	resized = {i: scale[mat.name] for i, mat in enumerate(thing.data.materials) if mat.name in scale}
	if not resized:
		continue
	mesh = bmesh.new()
	mesh.from_mesh(thing.data)
	uv = mesh.loops.layers.uv.active
	for face in mesh.faces:
		if face.material_index in resized:
			for loop in face.loops:
				loop[uv].uv *= resized[face.material_index]
	mesh.to_mesh(thing.data)
	mesh.free()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.pack_islands(rotate=True, margin=0.002)
bpy.ops.object.mode_set(mode="OBJECT")

bake_size = 2048 if FAST else 4096
bake = bpy.data.images.new("cabin-bake", bake_size, bake_size, float_buffer=True)
for mat in {mat for obj in [cabin] + movable for mat in obj.data.materials}:
	node = mat.node_tree.nodes.new("ShaderNodeTexImage")
	node.image = bake
	mat.node_tree.nodes.active = node
scene.cycles.samples = 128 if FAST else 512
scene.render.bake.margin = 16
# The glass and haze are drawn over the room, not lit onto it.
for obj in [glass] + haze_sheets:
	obj.hide_render = True
bpy.ops.object.bake(type="COMBINED")
for obj in [glass] + haze_sheets:
	obj.hide_render = False

# Saved with the scene's view transform applied, as the still is, so the
# browser shows it as is.
bake_path = os.path.join(ROOT, "scene", "cabin-bake.png")
bake.save_render(bake_path, scene=scene)
baked = bpy.data.materials.new("cabin-baked")
texture = baked.node_tree.nodes.new("ShaderNodeTexImage")
texture.image = bpy.data.images.load(bake_path)
baked.node_tree.links.new(texture.outputs["Color"], baked.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
for obj in [cabin] + movable:
	obj.data.materials.clear()
	obj.data.materials.append(baked)
for obj in space_objects + ship_parts + [guitar, ship]:
	bpy.data.objects.remove(obj)
card.hide_render = False
glass.data.materials[0] = glass_export
screen.data.materials[0] = material("laptop-screen-export", (0, 0, 0), emit=(0.035, 0.07, 0.1))
phone_screen.data.materials[0] = material("phone-screen-export", (0, 0, 0), emit=(0.02, 0.05, 0.08))
for sheet in haze_sheets:
	sheet.data.materials[0] = bpy.data.materials[f"{sheet.name}-export"]

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "scene", "cabin.blend"))
os.makedirs(os.path.join(ROOT, "public", "scene"), exist_ok=True)
# The exporter's compression keeps 12 bits of each position, a 2 mm grid in
# the cabin: lettering 1 mm in front of a card lands on the card and fights it
# for depth, and the Morse card's 3 mm dots lose their shape. 16 bits keeps
# them to a quarter of a millimetre. The setting isn't an export option, so
# this fails loudly if a Blender update moves it.
assert "EXP_FILTER_BITS" in inspect.getsource(gltf_meshopt.MeshoptEncoder.encode_attribute), "Blender's glTF exporter no longer reads EXP_FILTER_BITS: find its position precision again"
gltf_meshopt.EXP_FILTER_BITS = 16
bpy.ops.export_scene.gltf(
	filepath=os.path.join(ROOT, "public", "scene", "cabin.glb"),
	export_format="GLB",
	export_cameras=True,
	export_lights=False,
	export_image_format="WEBP",
	export_image_quality=85,
	export_meshopt_compression_enable=True,
	# Everything is drawn unlit, so normals would be dead weight.
	export_normals=False,
)
