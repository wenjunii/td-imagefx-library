uniform float uMix;
uniform float uOrder;
uniform float uAlphaFromLuma;
uniform float uMonochrome;

layout(location = 0) out vec4 fragColor;

vec3 reorder(vec3 value, float order)
{
    if (order < 0.5) return value.rgb;
    if (order < 1.5) return value.rbg;
    if (order < 2.5) return value.grb;
    if (order < 3.5) return value.gbr;
    if (order < 4.5) return value.brg;
    return value.bgr;
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 rgb = reorder(source.rgb, floor(uOrder + 0.5));
    float luma = dot(rgb, vec3(0.2126, 0.7152, 0.0722));
    rgb = mix(rgb, vec3(luma), step(0.5, uMonochrome));
    float alpha = mix(source.a, luma, step(0.5, uAlphaFromLuma));
    fragColor = TDOutputSwizzle(mix(source, vec4(rgb, alpha), clamp(uMix, 0.0, 1.0)));
}
