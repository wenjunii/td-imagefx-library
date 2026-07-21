uniform float uMix;
uniform vec3 uSlope;
uniform vec3 uOffset;
uniform vec3 uPower;
uniform float uSaturation;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 graded = pow(max(source.rgb * uSlope + uOffset, vec3(0.0)), max(uPower, vec3(0.0001)));
    float luma = dot(graded, vec3(0.2126, 0.7152, 0.0722));
    graded = mix(vec3(luma), graded, uSaturation);
    fragColor = TDOutputSwizzle(vec4(mix(source.rgb, graded, clamp(uMix, 0.0, 1.0)), source.a));
}
