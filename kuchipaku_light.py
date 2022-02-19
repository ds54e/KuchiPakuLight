bl_info = {
    "name": "Kuchi Paku Light",
    "author": "ds54e",
    "version": (1, 1, 1),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > KPL",
    "description": "Generate Kuchi-Paku animations from the sound sequences in the VSE",
    "warning": "",
    "doc_url": "",
    "category": "Animation",
}


import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty, PointerProperty

import numpy as np


class KuchiPakuPanel(bpy.types.Panel):
    bl_label = "Kuchi Paku Light"
    bl_idname = "OBJECT_PT_kuchipaku"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "KPL"

    def draw(self, context):
        layout = self.layout
        kp = context.scene.kuchipaku

        layout.prop(kp, "channel")
        layout.prop_search(kp, "object", context.scene, "objects")
        layout.prop(kp, "property")
        layout.prop(kp, "target_track")
        
        layout.row().separator()
        layout.prop(kp, "factor")
        layout.prop(kp, "offset")
        
        layout.row().separator()
        layout.prop(kp, "use_square")
        layout.prop(kp, "threshold")
        row = layout.row()
        row.prop(kp, "low_level")
        row.prop(kp, "high_level")
        
        layout.row().separator()
        layout.prop(kp, "is_select_all_enabled")
        layout.row().operator("object.kuchipaku_operator")


class KuchiPakuOperator(bpy.types.Operator):
    """Generate Kuchi-Paku animations from the sound sequences in the VSE"""
    bl_idname = "object.kuchipaku_operator"
    bl_label = "Generate"
    
    def execute(self, context):
        kp = context.scene.kuchipaku
        generate_kuchipaku(
            channel=kp.channel,
            object_name=kp.object.name,
            property_name=kp.property,
            target_track_name=kp.target_track,
            factor=kp.factor,
            offset=kp.offset,
            use_square=kp.use_square,
            threshold=kp.threshold,
            low_level=kp.low_level,
            high_level=kp.high_level,
            is_select_all_enabled=kp.is_select_all_enabled
        )
        return {"FINISHED"}


def generate_kuchipaku(
    channel = 1, # Y position of the sequence strip
    object_name = "Cube",
    property_name = "prop",
    target_track_name = "NlaTrack",
    factor = 100,
    offset = 0,
    use_square = True,
    threshold = 0.2,
    low_level=0,
    high_level=1,
    is_select_all_enabled=True
):
    audio_channel = 1
    freq_resolution = 1
    freq_range = (100, 1000)
    
    if object_name not in bpy.data.objects:
        return
    
    obj = bpy.data.objects[object_name]
    if property_name not in obj:
        return

    fps = (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base)
    depsgraph = bpy.context.evaluated_depsgraph_get()

    for seq in bpy.context.scene.sequence_editor.sequences:
        
        if (not is_select_all_enabled) and (not seq.select):
            continue
        
        if not (seq.type == "SOUND" and seq.channel ==  channel):
            continue
        
        action_already_exists = False
        for action in bpy.data.actions:
            if (action.name == seq.name):
                if (action.users > 0):
                    action_already_exists = True
                    break
                else:
                    bpy.data.actions.remove(action)
                    break
        if action_already_exists:
            continue

        sound = seq.sound.evaluated_get(depsgraph).factory
        rate, channel_count = sound.specs
        data = sound.data()[:, audio_channel-1]
        
        samples_per_frame = rate/fps
        buffer = np.zeros(int(samples_per_frame))
        amps = np.zeros(seq.frame_duration)
        
        # Get the amplitude in a given frequency range at each frame
        for i in range(seq.frame_duration):
            buffer.fill(0)
            i_start = int(samples_per_frame*i)
            i_end = int(samples_per_frame*(i+1))
            buffer = data[i_start:i_end]
            y = np.fft.rfft(buffer, n=int(rate/freq_resolution))
            i_start = int(freq_range[0]/freq_resolution)
            i_end = int(freq_range[1]/freq_resolution)
            amps[i] = np.mean(np.abs(y[i_start:i_end])/samples_per_frame)
       
        # Delete keyframes
        if obj.animation_data is not None:
            obj.animation_data.action = None
        
        # Add keyframes
        for i in range(len(amps)):
            if use_square:
                if (factor*amps[i] + offset) > threshold:
                    obj[property_name] = high_level
                else:
                    obj[property_name] = low_level
            else:
                obj[property_name] = factor*amps[i] + offset
            obj.keyframe_insert(data_path=f'["{property_name}"]', frame=seq.frame_start+1+i)
            
        if use_square:
          obj[property_name] = low_level
        else:
          obj[property_name] = offset
        obj.keyframe_insert(data_path=f'["{property_name}"]', frame=seq.frame_start)
        obj.keyframe_insert(data_path=f'["{property_name}"]', frame=seq.frame_start+len(amps))
        
        for fcurve in  obj.animation_data.action.fcurves:
            for keyframe in fcurve.keyframe_points:
                keyframe.interpolation = "CONSTANT"

        obj.animation_data.action.name = seq.name

        area_type = bpy.context.area.type
        bpy.context.area.type = "GRAPH_EDITOR"
        try:
          bpy.ops.graph.clean()
        except:
          pass
        bpy.context.area.type = area_type
        
        # Add the action to the target track
        target_track = None
        for track in obj.animation_data.nla_tracks:
            if track.name == target_track_name:
                target_track = track
                break
        else:
            target_track = obj.animation_data.nla_tracks.new()
            target_track.name = target_track_name
        
        is_overlapped = False
        start, end = tuple(map(int, obj.animation_data.action.frame_range))
        for strip in target_track.strips:
            if not (strip.frame_end < start or end < strip.frame_start):
                is_overlapped = True
                break;
        if is_overlapped:
            target_track = obj.animation_data.nla_tracks.new()
        
        target_track.strips.new(obj.animation_data.action.name, seq.frame_start, obj.animation_data.action)
        obj.animation_data.action = None
        

class KuchiPakuProperties(bpy.types.PropertyGroup):
    channel: IntProperty(
        name = "Channel",
        description="Y position of the sequence strip",
        default = 1,
        min = 1,
        soft_max = 16
    )
    
    factor: FloatProperty(
        name = "Factor",
        default = 100,
        soft_min = 0.0,
        step=1000
    )
    
    offset: FloatProperty(
        name = "Offset",
        default = 0.0,
        step=10
    )
    
    use_square: BoolProperty(
        name = "Square",
        default = True
    )
    
    threshold: FloatProperty(
        name = "Threshold",
        default = 0.2,
        step=10
    )
    
    high_level: IntProperty(
        name = "High",
        default = 1,
        soft_min = -16,
        soft_max = 16
    )
    
    low_level: IntProperty(
        name = "Low",
        default = 0,
        soft_min = -16,
        soft_max = 16
    )
    
    object: PointerProperty(
        name = "Object",
        type=bpy.types.Object
    )
    
    property: StringProperty(
        name = "Property"
    )
    
    target_track: StringProperty(
        name = "Track"
    )
    
    is_select_all_enabled: BoolProperty(
        name = "Select All",
        default = True
    )
    
    
def register():
    bpy.utils.register_class(KuchiPakuProperties)
    bpy.types.Scene.kuchipaku = PointerProperty(type=KuchiPakuProperties)
    bpy.utils.register_class(KuchiPakuPanel)
    bpy.utils.register_class(KuchiPakuOperator)


def unregister():
    bpy.utils.unregister_class(KuchiPakuProperties)
    bpy.utils.unregister_class(KuchiPakuPanel)
    bpy.utils.unregister_class(KuchiPakuOperator)
    del bpy.types.Scene.kuchipaku


if __name__ == "__main__":
    register()
