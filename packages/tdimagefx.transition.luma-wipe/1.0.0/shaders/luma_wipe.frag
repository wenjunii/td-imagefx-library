layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uProgress;
uniform float uSoftness;
uniform float uLumaBias;
uniform float uInvert;

void main()
{
    vec2 uv = vUV.st;
    vec4 imageA = texture(sTD2DInputs[0], uv);
    vec4 imageB = texture(sTD2DInputs[1], uv);

    float luma = dot(imageA.rgb, vec3(0.2126, 0.7152, 0.0722));
    luma = clamp(luma + uLumaBias, 0.0, 1.0);
    luma = mix(luma, 1.0 - luma, step(0.5, uInvert));
    float progress = clamp(uProgress, 0.0, 1.0);
    float softness = max(uSoftness, 0.0001);
    float coordinate = 1.0 - luma;
    float reveal = 1.0 - smoothstep(progress - softness, progress + softness, coordinate);
    reveal = progress <= 0.0 ? 0.0 : (progress >= 1.0 ? 1.0 : reveal);

    vec4 effect = mix(imageA, imageB, reveal);
    fragColor = TDOutputSwizzle(mix(imageA, effect, clamp(uMix, 0.0, 1.0)));
}
