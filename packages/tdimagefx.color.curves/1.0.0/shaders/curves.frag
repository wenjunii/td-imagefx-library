uniform float uMix;
uniform vec3 uShadows;
uniform vec3 uHighlights;
uniform float uPreserveLuma;

layout(location = 0) out vec4 fragColor;

vec3 cubicCurve(vec3 value)
{
    vec3 t = clamp(value, 0.0, 1.0);
    vec3 oneMinusT = 1.0 - t;
    vec3 curved = 3.0 * oneMinusT * oneMinusT * t * uShadows
        + 3.0 * oneMinusT * t * t * uHighlights
        + t * t * t;
    return curved + max(value - 1.0, 0.0) + min(value, 0.0);
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 curved = cubicCurve(source.rgb);
    float sourceLuma = dot(source.rgb, vec3(0.2126, 0.7152, 0.0722));
    float curvedLuma = dot(curved, vec3(0.2126, 0.7152, 0.0722));
    curved += vec3((sourceLuma - curvedLuma) * uPreserveLuma);
    fragColor = TDOutputSwizzle(vec4(mix(source.rgb, curved, clamp(uMix, 0.0, 1.0)), source.a));
}
