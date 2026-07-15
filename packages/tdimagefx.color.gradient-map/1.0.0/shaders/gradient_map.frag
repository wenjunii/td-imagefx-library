layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform vec4 uShadowColor;
uniform vec4 uMidColor;
uniform vec4 uHighlightColor;
uniform float uMidpoint;
uniform float uSmoothness;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    float luma = clamp(dot(source.rgb, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
    float midpoint = clamp(uMidpoint, 0.0001, 0.9999);
    float lowT = clamp(luma / midpoint, 0.0, 1.0);
    float highT = clamp((luma - midpoint) / (1.0 - midpoint), 0.0, 1.0);
    float blendWidth = max(uSmoothness, 0.0001);
    lowT = smoothstep(0.0, 1.0, lowT);
    highT = smoothstep(0.0, 1.0, highT);
    vec3 lowColor = mix(uShadowColor.rgb, uMidColor.rgb, lowT);
    vec3 highColor = mix(uMidColor.rgb, uHighlightColor.rgb, highT);
    float branch = smoothstep(midpoint - blendWidth, midpoint + blendWidth, luma);
    vec3 mapped = mix(lowColor, highColor, branch);
    vec4 effect = vec4(mapped, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
