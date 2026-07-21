uniform float uMix;
uniform float uFrameAspect;
uniform float uMode;
uniform vec2 uAlignment;
uniform vec4 uBackground;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 sourceSize = vec2(textureSize(sTD2DInputs[0], 0));
    float sourceAspect = sourceSize.x / max(sourceSize.y, 1.0);
    float frameAspect = max(uFrameAspect, 0.0001);
    vec2 scale = vec2(1.0);
    float mode = floor(uMode + 0.5);
    if (mode < 0.5) {
        scale = sourceAspect > frameAspect ? vec2(1.0, frameAspect / sourceAspect) : vec2(sourceAspect / frameAspect, 1.0);
    } else if (mode < 1.5) {
        scale = sourceAspect > frameAspect ? vec2(sourceAspect / frameAspect, 1.0) : vec2(1.0, frameAspect / sourceAspect);
    }
    vec2 origin = (1.0 - scale) * clamp(uAlignment, 0.0, 1.0);
    vec2 sampleUv = (uv - origin) / max(scale, vec2(0.0001));
    bool inside = all(greaterThanEqual(sampleUv, vec2(0.0))) && all(lessThanEqual(sampleUv, vec2(1.0)));
    vec4 framed = inside ? texture(sTD2DInputs[0], sampleUv) : uBackground;
    fragColor = TDOutputSwizzle(mix(source, framed, clamp(uMix, 0.0, 1.0)));
}
