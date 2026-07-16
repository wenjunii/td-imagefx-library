uniform float uMix;
uniform vec2 uTranslate;
uniform vec2 uScale;
uniform float uRotation;
uniform vec2 uPivot;
uniform float uRepeat;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 scale = max(abs(uScale), vec2(0.0001));
    float c = cos(-uRotation);
    float s = sin(-uRotation);
    vec2 local = uv - uPivot - uTranslate;
    local = mat2(c, -s, s, c) * local;
    vec2 sampleUv = local / scale + uPivot;
    bool inside = all(greaterThanEqual(sampleUv, vec2(0.0))) && all(lessThanEqual(sampleUv, vec2(1.0)));
    sampleUv = mix(sampleUv, fract(sampleUv), step(0.5, uRepeat));
    vec4 transformed = texture(sTD2DInputs[0], sampleUv);
    if (uRepeat < 0.5 && !inside) {
        transformed = vec4(0.0);
    }
    fragColor = TDOutputSwizzle(mix(source, transformed, clamp(uMix, 0.0, 1.0)));
}
